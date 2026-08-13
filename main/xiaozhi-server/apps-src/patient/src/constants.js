const ensureDeviceId = () => {
  let id = localStorage.getItem('hospice_device_id') || localStorage.getItem('xz_tester_deviceMac');
  if (id === 'default') id = localStorage.getItem('xz_tester_deviceMac') || '';
  if (!id) {
    const hex = '0123456789ABCDEF';
    id = Array.from({ length: 6 }, () =>
      hex[Math.floor(Math.random() * 16)] + hex[Math.floor(Math.random() * 16)]
    ).join(':');
  }
  localStorage.setItem('hospice_device_id', id);
  localStorage.setItem('xz_tester_deviceMac', id);
  return id;
};

// 设备 ID：患者端、安安 WebSocket、家属端必须一致
export const DEVICE_ID = ensureDeviceId();
// 患者名（回复署名用）
export const PATIENT_NAME = localStorage.getItem('hospice_patient_name') || '我';
