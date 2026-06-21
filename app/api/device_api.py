import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import require_staff_session
from app.core.database import get_db
from app.model.db_model import DeviceInfo
from app.schema.schema_ import DeviceCreateRequest, DeviceResponse, DeviceUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
    dependencies=[Depends(require_staff_session)],
)


@router.get("", response_model=list[DeviceResponse])
async def list_devices(db: Session = Depends(get_db)) -> list[DeviceResponse]:
    devices = db.query(DeviceInfo).order_by(DeviceInfo.device_id.asc()).all()
    return [DeviceResponse.model_validate(device, from_attributes=True) for device in devices]


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    data: DeviceCreateRequest,
    db: Session = Depends(get_db),
) -> DeviceResponse:
    if db.get(DeviceInfo, data.device_id) is not None:
        raise HTTPException(status_code=409, detail="device_already_exists")
    device = DeviceInfo(
        device_id=data.device_id,
        station_name=data.station_name,
        location=data.location,
    )
    db.add(device)
    try:
        db.commit()
        db.refresh(device)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="device_already_exists")
    logger.info("device_created | device=%s", device.device_id)
    return DeviceResponse.model_validate(device, from_attributes=True)


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    data: DeviceUpdateRequest,
    device_id: str = Path(..., pattern=r"^[A-Z]+_\d+$"),
    db: Session = Depends(get_db),
) -> DeviceResponse:
    device = db.get(DeviceInfo, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device_not_found")
    device.station_name = data.station_name
    device.location = data.location
    db.commit()
    db.refresh(device)
    logger.info("device_updated | device=%s", device.device_id)
    return DeviceResponse.model_validate(device, from_attributes=True)
