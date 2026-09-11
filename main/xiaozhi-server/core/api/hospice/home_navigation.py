"""Bound the paid ASR window independently of the browser timer."""
import asyncio
from contextlib import suppress

HOME_LISTEN_SECONDS = 20


async def stop_home_listening(conn):
    conn.hospice_home_listening = False
    conn.hospice_home_rearm_asr = False
    timer = getattr(conn, "hospice_home_timer", None)
    if timer:
        timer.cancel()
        conn.hospice_home_timer = None
    # Cancel an in-flight ASR connect/send before closing the socket.
    task = getattr(conn, "hospice_home_audio_task", None)
    if task and task is not asyncio.current_task() and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    prepare_task = getattr(conn, "hospice_home_prepare_task", None)
    if prepare_task and prepare_task is not asyncio.current_task() and not prepare_task.done():
        prepare_task.cancel()
        with suppress(asyncio.CancelledError):
            await prepare_task
    conn.hospice_home_prepare_task = None
    asr = getattr(conn, "asr", None)
    forward = getattr(asr, "forward_task", None)
    if forward and forward is not asyncio.current_task() and not forward.done():
        forward.cancel()
        with suppress(asyncio.CancelledError):
            await forward
    if asr and hasattr(asr, "stop_ws_connection"):
        asr.stop_ws_connection()
    conn.reset_audio_states()


def start_home_listening(conn):
    if getattr(conn, "hospice_home_listening", False):
        return  # Repeated messages must not extend the deadline.
    conn.hospice_home_listening = True
    conn.hospice_home_timer = asyncio.get_running_loop().call_later(
        HOME_LISTEN_SECONDS,
        lambda: asyncio.create_task(stop_home_listening(conn)),
    )
    prepare = getattr(getattr(conn, "asr", None), "prepare_stream", None)
    if callable(prepare):
        conn.hospice_home_prepare_task = asyncio.create_task(prepare(conn))
