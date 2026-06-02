export const DEVICE_ID = localStorage.getItem('hospice_device_id') || '';
export const FAMILY_ID = localStorage.getItem('hospice_family_id') || '';
export const SENDER_NAME = localStorage.getItem('hospice_sender_name') || '';

export const hasPairing = () => Boolean(
  localStorage.getItem('hospice_device_id') &&
  localStorage.getItem('hospice_family_id') &&
  localStorage.getItem('hospice_sender_name')
);

export const clearPairing = () => {
  localStorage.removeItem('hospice_device_id');
  localStorage.removeItem('hospice_family_id');
  localStorage.removeItem('hospice_sender_name');
};
