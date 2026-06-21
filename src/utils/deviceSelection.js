export const DEVICE_STORAGE_KEY = "sign-kiosk.device-id";
export const DEVICE_ID_PATTERN = /^[A-Z]+_\d+$/;

export const getConfiguredDeviceId = () => {
  const fallback = (process.env.REACT_APP_KIOSK_DEVICE_ID || "").trim();
  try {
    const stored = window.localStorage.getItem(DEVICE_STORAGE_KEY)?.trim() || "";
    return DEVICE_ID_PATTERN.test(stored) ? stored : fallback;
  } catch {
    return fallback;
  }
};

export const saveConfiguredDeviceId = (deviceId) => {
  if (!DEVICE_ID_PATTERN.test(deviceId)) throw new Error("invalid_device_id_format");
  window.localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
};
