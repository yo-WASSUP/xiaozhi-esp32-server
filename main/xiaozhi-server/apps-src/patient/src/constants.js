// 设备 ID：患者与家属端必须一致
export const DEVICE_ID = localStorage.getItem('hospice_device_id') || 'default';
// 患者名（回复署名用）
export const PATIENT_NAME = localStorage.getItem('hospice_patient_name') || '我';
