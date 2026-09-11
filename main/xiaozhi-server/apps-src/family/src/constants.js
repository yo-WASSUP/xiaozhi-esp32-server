export const DEVICE_ID = localStorage.getItem('family_hospice_device_id') || '';
export const FAMILY_ID = localStorage.getItem('family_hospice_family_id') || '';
export const SENDER_NAME = localStorage.getItem('family_hospice_sender_name') || '';

export const hasPairing = () => Boolean(
  localStorage.getItem('family_hospice_device_id') &&
  localStorage.getItem('family_hospice_family_id') &&
  localStorage.getItem('family_hospice_sender_name')
);

export const clearPairing = () => {
  localStorage.removeItem('family_hospice_device_id');
  localStorage.removeItem('family_hospice_family_id');
  localStorage.removeItem('family_hospice_sender_name');
};
