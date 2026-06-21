import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import "./DeviceSettingsModal.css";

const SESSION_PATH = "/api/auth/me";
const LOGIN_PATH = "/api/auth/login";
const LOGOUT_PATH = "/api/auth/logout";
const DEVICES_PATH = "/api/devices";
const EMPTY_FORM = { device_id: "", station_name: "", location: "" };

export default function DeviceSettingsModal({ currentDeviceId, onSelect, onClose }) {
  const [authenticated, setAuthenticated] = useState(null);
  const [password, setPassword] = useState("");
  const [devices, setDevices] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadDevices = useCallback(async () => {
    const response = await axios.get(DEVICES_PATH, { withCredentials: true, timeout: 5000 });
    const items = Array.isArray(response.data) ? response.data : [];
    setDevices(items);
    const selected = items.find((item) => item.device_id === currentDeviceId) || items[0];
    if (selected) setForm({ ...selected, location: selected.location || "" });
  }, [currentDeviceId]);

  useEffect(() => {
    let stopped = false;
    axios.get(SESSION_PATH, { withCredentials: true, timeout: 5000 })
      .then(async () => {
        if (stopped) return;
        setAuthenticated(true);
        await loadDevices();
      })
      .catch(() => {
        if (!stopped) setAuthenticated(false);
      });
    return () => { stopped = true; };
  }, [loadDevices]);

  const login = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await axios.post(LOGIN_PATH, { password }, { withCredentials: true, timeout: 5000 });
      setPassword("");
      setAuthenticated(true);
      await loadDevices();
    } catch (loginError) {
      setError(loginError?.response?.status === 401
        ? "관리자 비밀번호가 올바르지 않습니다."
        : "관리자 인증을 완료하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const selectForEdit = (device) => {
    setCreating(false);
    setForm({ ...device, location: device.location || "" });
    setError("");
  };

  const startCreate = () => {
    setCreating(true);
    setForm(EMPTY_FORM);
    setError("");
  };

  const saveDevice = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = {
      station_name: form.station_name.trim(),
      location: form.location.trim() || null,
    };
    try {
      if (creating) {
        await axios.post(DEVICES_PATH, {
          device_id: form.device_id.trim(),
          ...payload,
        }, { withCredentials: true, timeout: 5000 });
      } else {
        await axios.put(`${DEVICES_PATH}/${form.device_id}`, payload, {
          withCredentials: true,
          timeout: 5000,
        });
      }
      await loadDevices();
      setCreating(false);
    } catch (saveError) {
      const message = saveError?.response?.data?.message;
      setError(message === "device_already_exists"
        ? "이미 등록된 장치 ID입니다."
        : "장치 정보를 저장하지 못했습니다. 형식과 입력값을 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  };

  const closeSecurely = async () => {
    if (authenticated) {
      try {
        await axios.post(LOGOUT_PATH, {}, { withCredentials: true, timeout: 3000 });
      } catch {
        // Closing the protected panel must not be blocked by a logout network failure.
      }
    }
    onClose();
  };

  const selectDeviceSecurely = async () => {
    setBusy(true);
    setError("");
    try {
      await axios.post(LOGOUT_PATH, {}, { withCredentials: true, timeout: 3000 });
      onSelect(form.device_id);
    } catch {
      setError("관리자 세션을 안전하게 종료하지 못해 장치를 변경하지 않았습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="device-modal-backdrop" role="presentation">
      <section className="device-modal" role="dialog" aria-modal="true" aria-labelledby="device-modal-title">
        <header>
          <h2 id="device-modal-title">키오스크 장치 설정</h2>
          <button type="button" className="device-close" onClick={closeSecurely}>닫기</button>
        </header>

        {authenticated === null && <p>관리자 인증 상태를 확인하고 있습니다.</p>}

        {authenticated === false && (
          <form className="device-login" onSubmit={login}>
            <p>장치 변경은 관리자 인증 후 사용할 수 있습니다.</p>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="관리자 비밀번호"
              autoComplete="current-password"
              required
            />
            <button type="submit" disabled={busy}>{busy ? "인증 중" : "인증"}</button>
          </form>
        )}

        {authenticated === true && (
          <div className="device-settings-content">
            <aside className="device-list" aria-label="등록된 장치">
              {devices.map((device) => (
                <button
                  type="button"
                  key={device.device_id}
                  className={form.device_id === device.device_id && !creating ? "selected" : ""}
                  onClick={() => selectForEdit(device)}
                >
                  <strong>{device.device_id}</strong>
                  <span>{device.station_name} · {device.location || "위치 미등록"}</span>
                </button>
              ))}
              <button type="button" className="device-add" onClick={startCreate}>+ 새 장치 등록</button>
            </aside>

            <form className="device-form" onSubmit={saveDevice}>
              <label>
                장치 ID
                <input
                  value={form.device_id}
                  onChange={(event) => setForm({ ...form, device_id: event.target.value.toUpperCase() })}
                  placeholder="SEOUL_01"
                  pattern="[A-Z]+_[0-9]+"
                  disabled={!creating}
                  required
                />
              </label>
              <label>
                역명
                <input
                  value={form.station_name}
                  onChange={(event) => setForm({ ...form, station_name: event.target.value })}
                  maxLength={100}
                  required
                />
              </label>
              <label>
                위치
                <input
                  value={form.location}
                  onChange={(event) => setForm({ ...form, location: event.target.value })}
                  maxLength={100}
                  placeholder="예: 1번 창구"
                />
              </label>
              <div className="device-form-actions">
                <button type="submit" disabled={busy || !form.device_id || !form.station_name}>
                  {busy ? "저장 중" : creating ? "등록" : "정보 수정"}
                </button>
                {!creating && form.device_id && (
                  <button type="button" onClick={selectDeviceSecurely} disabled={busy}>
                    이 장치 사용
                  </button>
                )}
              </div>
            </form>
          </div>
        )}

        {error && <p className="device-modal-error" role="alert">{error}</p>}
      </section>
    </div>
  );
}
