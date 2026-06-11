"""Composed request handler for the hospice REST API."""
from core.api.hospice.base import HospiceBaseMixin
from core.api.hospice.calls import HospiceCallsMixin
from core.api.hospice.interview_audio import HospiceInterviewAudioMixin
from core.api.hospice.legacy_card import HospiceLegacyCardMixin
from core.api.hospice.media import HospiceMediaMixin
from core.api.hospice.messages import HospiceMessagesMixin
from core.api.hospice.video import HospiceVideoMixin
from core.api.hospice.voice import HospiceVoiceMixin
from core.api.hospice.wakeword import HospiceWakeWordMixin


class HospiceFamilyHandler(
    HospiceVoiceMixin,
    HospiceMessagesMixin,
    HospiceMediaMixin,
    HospiceCallsMixin,
    HospiceInterviewAudioMixin,
    HospiceLegacyCardMixin,
    HospiceVideoMixin,
    HospiceWakeWordMixin,
    HospiceBaseMixin,
):
    """Family/patient API handler composed from focused endpoint mixins."""

    pass
