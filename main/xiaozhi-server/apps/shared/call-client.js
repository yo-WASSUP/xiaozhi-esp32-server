/**
 * 安宁疗护 - 通话客户端（家属/患者共用）
 *
 * 使用：
 *   const client = new CallClient({
 *     deviceId: 'default',
 *     role: 'family',          // 'family' | 'patient'
 *     onIncoming: ({fromName, callType}) => ...,     // 对方发起呼叫
 *     onAccepted: () => ...,                          // 己方呼出被接听
 *     onRejected: () => ...,                          // 己方呼出被拒
 *     onEnded: (reason) => ...,                       // 通话结束/对端断线
 *     onLocalStream: (stream) => ...,                 // 本地媒体流（挂到 <video muted>）
 *     onRemoteStream: (stream) => ...,                // 对端媒体流（挂到 <video>/<audio>）
 *     onState: (state) => ...,                        // 'idle'|'calling'|'ringing'|'connecting'|'active'
 *   });
 *   client.connect();                 // 启动 WebSocket（登录即连）
 *   client.placeCall({callType,fromName});  // 家属发起
 *   client.accept();  client.reject();      // 患者接/拒
 *   client.hangup();                         // 任一方挂断
 */
(function () {
  'use strict';

  const ICE_SERVERS = [
    { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] },
  ];

  class CallClient {
    constructor(opts) {
      this.deviceId = opts.deviceId;
      this.role = opts.role;
      this.handlers = {
        onIncoming: opts.onIncoming || (() => {}),
        onAccepted: opts.onAccepted || (() => {}),
        onRejected: opts.onRejected || (() => {}),
        onEnded: opts.onEnded || (() => {}),
        onLocalStream: opts.onLocalStream || (() => {}),
        onRemoteStream: opts.onRemoteStream || (() => {}),
        onState: opts.onState || (() => {}),
      };
      this.ws = null;
      this.pc = null;
      this.localStream = null;
      this.remoteStream = null;
      this.callType = 'audio';   // 'audio' | 'video'
      this.peerName = null;
      this.state = 'idle';
      this._pendingCandidates = [];  // 远端 ICE 等待 setRemoteDescription
    }

    _setState(s) {
      if (this.state === s) return;
      this.state = s;
      try { this.handlers.onState(s); } catch (e) { console.error(e); }
    }

    connect() {
      if (this.ws && (this.ws.readyState === 0 || this.ws.readyState === 1)) return;
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${proto}//${location.host}/api/hospice/call/ws?device_id=${encodeURIComponent(this.deviceId)}&role=${this.role}`;
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => console.log('[call] ws open');
      ws.onmessage = (ev) => this._onMessage(ev);
      ws.onclose = () => {
        console.log('[call] ws closed');
        this._cleanup('ws-closed');
        if (this._destroyed) return;
        // 3s 后重连，确保随时能接电话
        setTimeout(() => this.connect(), 3000);
      };
      ws.onerror = (e) => console.warn('[call] ws error', e);
    }

    _send(obj) {
      if (!this.ws || this.ws.readyState !== 1) {
        console.warn('[call] ws not open, drop', obj);
        return;
      }
      this.ws.send(JSON.stringify(obj));
    }

    async _onMessage(ev) {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      console.log('[call] recv', msg.type, msg);

      switch (msg.type) {
        case 'call-request': {
          // 对端发起呼叫（我是被叫）
          if (this.state !== 'idle') {
            this._send({ type: 'call-reject', reason: 'busy' });
            return;
          }
          this.callType = msg.call_type || 'audio';
          this.peerName = msg.from_name || null;
          this._setState('ringing');
          this.handlers.onIncoming({ fromName: this.peerName, callType: this.callType });
          break;
        }

        case 'call-accept': {
          // 对端接听了我发起的呼叫 → 我来造 offer
          if (this.state !== 'calling') return;
          this._setState('connecting');
          this.handlers.onAccepted();
          await this._prepareLocalMedia(this.callType);
          this._createPeerConnection();
          this.localStream.getTracks().forEach(t => this.pc.addTrack(t, this.localStream));
          const offer = await this.pc.createOffer();
          await this.pc.setLocalDescription(offer);
          this._send({ type: 'offer', sdp: this.pc.localDescription });
          break;
        }

        case 'call-reject': {
          this.handlers.onRejected(msg.reason);
          this._cleanup('rejected');
          break;
        }

        case 'offer': {
          // 被叫收到 offer → 造 answer
          await this._prepareLocalMedia(this.callType);
          this._createPeerConnection();
          this.localStream.getTracks().forEach(t => this.pc.addTrack(t, this.localStream));
          await this.pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
          await this._drainPendingCandidates();
          const answer = await this.pc.createAnswer();
          await this.pc.setLocalDescription(answer);
          this._send({ type: 'answer', sdp: this.pc.localDescription });
          this._setState('connecting');
          break;
        }

        case 'answer': {
          if (!this.pc) return;
          await this.pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
          await this._drainPendingCandidates();
          break;
        }

        case 'ice': {
          if (!msg.candidate) return;
          const cand = new RTCIceCandidate(msg.candidate);
          if (this.pc && this.pc.remoteDescription) {
            try { await this.pc.addIceCandidate(cand); } catch (e) { console.warn(e); }
          } else {
            this._pendingCandidates.push(cand);
          }
          break;
        }

        case 'call-end': {
          this._cleanup(msg.reason || 'peer-end');
          break;
        }

        case 'peer-absent': {
          if (this.state === 'calling') {
            this.handlers.onEnded('peer-absent');
            this._cleanup('peer-absent');
          }
          break;
        }
      }
    }

    async _prepareLocalMedia(callType) {
      if (this.localStream) return;
      const constraints = callType === 'video'
        ? { audio: true, video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' } }
        : { audio: true, video: false };
      this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
      this.handlers.onLocalStream(this.localStream);
    }

    _createPeerConnection() {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      pc.onicecandidate = (e) => {
        if (e.candidate) this._send({ type: 'ice', candidate: e.candidate });
      };
      pc.ontrack = (e) => {
        if (!this.remoteStream) {
          this.remoteStream = new MediaStream();
          this.handlers.onRemoteStream(this.remoteStream);
        }
        this.remoteStream.addTrack(e.track);
      };
      pc.onconnectionstatechange = () => {
        console.log('[call] pc state:', pc.connectionState);
        if (pc.connectionState === 'connected') {
          this._setState('active');
        } else if (['disconnected', 'failed', 'closed'].includes(pc.connectionState)) {
          if (this.state === 'active' || this.state === 'connecting') {
            this._cleanup(pc.connectionState);
          }
        }
      };
      this.pc = pc;
    }

    async _drainPendingCandidates() {
      const list = this._pendingCandidates;
      this._pendingCandidates = [];
      for (const c of list) {
        try { await this.pc.addIceCandidate(c); } catch (e) { console.warn(e); }
      }
    }

    // ── 外部 API ──

    async placeCall({ callType = 'audio', fromName = '' } = {}) {
      if (this.state !== 'idle') return false;
      this.callType = callType;
      this._setState('calling');
      // 先拿麦克风/摄像头权限（在这里就拿，否则用户要等到 accept 后才弹权限框）
      try {
        await this._prepareLocalMedia(callType);
      } catch (e) {
        console.error('media error', e);
        this._cleanup('media-error');
        throw e;
      }
      this._send({ type: 'call-request', call_type: callType, from_name: fromName });
      return true;
    }

    async accept() {
      if (this.state !== 'ringing') return;
      this._setState('connecting');
      this._send({ type: 'call-accept' });
    }

    reject(reason) {
      if (this.state !== 'ringing') return;
      this._send({ type: 'call-reject', reason: reason || 'user-reject' });
      this._cleanup('rejected-local');
    }

    hangup() {
      if (this.state === 'idle') return;
      this._send({ type: 'call-end', reason: 'user-hangup' });
      this._cleanup('user-hangup');
    }

    disconnect() {
      this._destroyed = true;
      if (this.ws) {
        this.ws.onclose = null; // 避免触发重连逻辑
        this.ws.close();
        this.ws = null;
      }
      this._cleanup('user-disconnect');
    }

    _cleanup(reason) {
      const wasActive = this.state !== 'idle';
      if (this.pc) {
        try { this.pc.close(); } catch (_) {}
        this.pc = null;
      }
      if (this.localStream) {
        this.localStream.getTracks().forEach(t => t.stop());
        this.localStream = null;
      }
      this.remoteStream = null;
      this._pendingCandidates = [];
      this.callType = 'audio';
      this.peerName = null;
      this._setState('idle');
      if (wasActive) {
        try { this.handlers.onEnded(reason); } catch (e) { console.error(e); }
      }
    }

    // 辅助：通话中静音 / 开关摄像头
    toggleMute(muted) {
      if (!this.localStream) return;
      this.localStream.getAudioTracks().forEach(t => { t.enabled = !muted; });
    }
    toggleCamera(off) {
      if (!this.localStream) return;
      this.localStream.getVideoTracks().forEach(t => { t.enabled = !off; });
    }
  }

  window.CallClient = CallClient;
})();
