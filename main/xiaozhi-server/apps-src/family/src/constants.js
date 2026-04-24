// 设备 ID：患者与家属端必须一致；后续可做"绑定患者"流程
export const DEVICE_ID = localStorage.getItem('hospice_device_id') || 'default';
// 本家属的署名（决定会话线 contact_name）
export const SENDER_NAME = localStorage.getItem('hospice_sender_name') || '家属';
