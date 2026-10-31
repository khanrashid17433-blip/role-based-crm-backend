from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from bson import ObjectId
from datetime import datetime, date
from Models.holiday import Holiday
import logging

logger = logging.getLogger(__name__)
from uuid import UUID
from Utility.auth_helpers import verify_tenant_admin
from Schema.holiday import HolidayCreate, HolidayUpdate

router = APIRouter(
    prefix="/api/holidays",
    tags=["Holidays"]
)


# -----------------------------
# ✅ GET ALL
# -----------------------------
@router.get("/", status_code=status.HTTP_200_OK)
async def get_holidays():
    holidays = await Holiday.find_all().to_list()
    return {
        "success": True,
        "data": holidays
    }


# -----------------------------
# ✅ CREATE
# -----------------------------

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_holiday(
    data: HolidayCreate,
    current_user=Depends(verify_tenant_admin)  # ✅ only admin/hr
):
    try:
        tenant_id = UUID(current_user.get("tid"))

        holiday_dict = data.dict()

        # ✅ convert date → datetime
        holiday_dict["holiday_date"] = datetime.combine(
            holiday_dict["holiday_date"], datetime.min.time()
        )

        holiday = Holiday(
            **holiday_dict,
            tenant_id=tenant_id
        )

        await holiday.insert()

        return {
            "message": "Holiday Created Successfully",
            "data": holiday
        }

    except Exception as e:
        logger.error(f"Create holiday failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error"
        )
# -----------------------------
# ✅ UPDATE
# -----------------------------
@router.put("/{id}", status_code=status.HTTP_200_OK)
async def update_holiday(id: str, data: HolidayUpdate):

    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID")

    holiday = await Holiday.get(id)

    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    update_data = data.model_dump(exclude_unset=True)

    # ✅ FIX HERE (MOST IMPORTANT)
    if "holiday_date" in update_data:
        if isinstance(update_data["holiday_date"], date):
            update_data["holiday_date"] = datetime.combine(
                update_data["holiday_date"], datetime.min.time()
            )

    await holiday.set(update_data)
    await holiday.save()

    return {
        "success": True,
        "message": "Holiday updated"
    }
# -----------------------------
# ✅ DELETE
# -----------------------------
@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_holiday(id: str):

    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID")

    holiday = await Holiday.get(id)

    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    await holiday.delete()

    return {
        "success": True,
        "message": "Holiday deleted"
    }