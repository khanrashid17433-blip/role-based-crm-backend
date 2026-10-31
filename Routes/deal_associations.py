from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional, List
from uuid import UUID
import logging

from Models.crm_deal_associations import CrmDealContact, CrmDealTeam, CrmDealLineItem, DealContactRole, DealTeamRole
from Models.crm import CrmDeal
from Models.crm_contacts import CrmContact
from Models.tenant_user import User
from Utility.auth_helpers import verify_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/deals", tags=["Deal Associations"])


# ── Helper ───────────────────────────────────────────────────────────────────

def _serialize_contact(c: CrmDealContact) -> Dict[str, Any]:
    return {
        "id": str(c.id),
        "deal_id": str(c.deal_id),
        "contact_id": str(c.contact_id) if c.contact_id else None,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "job_title": c.job_title,
        "linkedin_url": c.linkedin_url,
        "company_name": c.company_name,
        "role": c.role.value if hasattr(c.role, "value") else c.role,
        "is_primary": c.is_primary,
        "notes": c.notes,
        "created_at": c.created_at.isoformat(),
    }


def _serialize_team_member(m: CrmDealTeam) -> Dict[str, Any]:
    return {
        "id": str(m.id),
        "deal_id": str(m.deal_id),
        "user_id": str(m.user_id),
        "user_name": m.user_name,
        "user_email": m.user_email,
        "role": m.role.value if hasattr(m.role, "value") else m.role,
        "added_at": m.added_at.isoformat(),
    }


def _serialize_line_item(item: CrmDealLineItem) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "deal_id": str(item.deal_id),
        "product_name": item.product_name,
        "product_id": str(item.product_id) if item.product_id else None,
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "discount_pct": item.discount_pct,
        "tax_pct": item.tax_pct,
        "total": item.total,
        "sort_order": item.sort_order,
        "created_at": item.created_at.isoformat(),
    }


# ── Deal Contacts ─────────────────────────────────────────────────────────────

@router.get("/{deal_id}/contacts", summary="Get Deal Contacts")
async def get_deal_contacts(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        contacts = await CrmDealContact.find(
            CrmDealContact.deal_id == UUID(deal_id),
            CrmDealContact.tenant_id == tenant_id,
        ).sort(CrmDealContact.created_at).to_list()
        return [_serialize_contact(c) for c in contacts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/contacts", summary="Add Contact to Deal", status_code=status.HTTP_201_CREATED)
async def add_deal_contact(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get("sub"))
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))

        # Verify deal exists
        deal = await CrmDeal.find_one(CrmDeal.id == UUID(deal_id), CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        # If primary is set, unset existing primary
        is_primary = data.get("is_primary", False)
        if is_primary:
            existing_primaries = await CrmDealContact.find(
                CrmDealContact.deal_id == UUID(deal_id),
                CrmDealContact.is_primary == True,
            ).to_list()
            for ep in existing_primaries:
                ep.is_primary = False
                await ep.save()

        # Resolve contact details from contact_id if provided
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        email = data.get("email")
        phone = data.get("phone")
        job_title = data.get("job_title")
        linkedin_url = data.get("linkedin_url")
        company_name = data.get("company_name")
        contact_id = None

        if data.get("contact_id"):
            contact_id = UUID(data["contact_id"])
            contact = await CrmContact.find_one(CrmContact.id == contact_id)
            if contact:
                first_name = contact.first_name
                last_name = contact.last_name or ""
                email = contact.email
                phone = contact.phone or phone
                job_title = contact.job_title or job_title
                linkedin_url = contact.linkedin_url or linkedin_url
                company_name = contact.company_name or company_name

        try:
            role = DealContactRole(data.get("role", "primary_contact"))
        except ValueError:
            role = DealContactRole.primary_contact

        assoc = CrmDealContact(
            deal_id=UUID(deal_id),
            tenant_id=tenant_id,
            contact_id=contact_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            job_title=job_title,
            linkedin_url=linkedin_url,
            company_name=company_name,
            role=role,
            is_primary=is_primary,
            notes=data.get("notes"),
            created_by=user_id,
        )
        await assoc.insert()

        return {"message": "Contact added to deal", "id": str(assoc.id), "contact": _serialize_contact(assoc)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{deal_id}/contacts/{assoc_id}", summary="Update Deal Contact Association")
async def update_deal_contact(deal_id: str, assoc_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        assoc = await CrmDealContact.find_one(
            CrmDealContact.id == UUID(assoc_id),
            CrmDealContact.deal_id == UUID(deal_id),
            CrmDealContact.tenant_id == tenant_id,
        )
        if not assoc:
            raise HTTPException(status_code=404, detail="Association not found")

        if "role" in data:
            try:
                assoc.role = DealContactRole(data["role"])
            except ValueError:
                pass
        if "is_primary" in data:
            new_primary = bool(data["is_primary"])
            if new_primary and not assoc.is_primary:
                # Unset others
                others = await CrmDealContact.find(
                    CrmDealContact.deal_id == UUID(deal_id),
                    CrmDealContact.is_primary == True,
                ).to_list()
                for o in others:
                    o.is_primary = False
                    await o.save()
            assoc.is_primary = new_primary
        if "notes" in data:
            assoc.notes = data["notes"]
        for field in ("first_name", "last_name", "email", "phone", "job_title", "linkedin_url", "company_name"):
            if field in data:
                setattr(assoc, field, data[field])

        from datetime import datetime
        assoc.updated_at = datetime.utcnow()
        await assoc.save()
        return {"message": "Contact updated", "contact": _serialize_contact(assoc)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{deal_id}/contacts/{assoc_id}", summary="Remove Contact from Deal")
async def remove_deal_contact(deal_id: str, assoc_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        assoc = await CrmDealContact.find_one(
            CrmDealContact.id == UUID(assoc_id),
            CrmDealContact.deal_id == UUID(deal_id),
            CrmDealContact.tenant_id == tenant_id,
        )
        if not assoc:
            raise HTTPException(status_code=404, detail="Association not found")
        await assoc.delete()
        return {"message": "Contact removed from deal"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{deal_id}/stakeholders", summary="Get Stakeholder Summary Counts")
async def get_deal_stakeholders(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        contacts = await CrmDealContact.find(
            CrmDealContact.deal_id == UUID(deal_id),
            CrmDealContact.tenant_id == tenant_id,
        ).to_list()

        role_counts: Dict[str, int] = {}
        for c in contacts:
            role_val = c.role.value if hasattr(c.role, "value") else str(c.role)
            role_counts[role_val] = role_counts.get(role_val, 0) + 1

        decision_makers = role_counts.get("decision_maker", 0)
        technical = role_counts.get("technical_contact", 0)
        finance = role_counts.get("finance_approver", 0)
        legal = role_counts.get("legal_approver", 0)
        others = len(contacts) - decision_makers - technical - finance - legal

        return {
            "total": len(contacts),
            "decision_makers": decision_makers,
            "technical_contacts": technical,
            "finance_contacts": finance,
            "legal_contacts": legal,
            "others": max(others, 0),
            "by_role": role_counts,
            "contacts": [_serialize_contact(c) for c in contacts],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Deal Team ─────────────────────────────────────────────────────────────────

@router.get("/{deal_id}/team", summary="Get Deal Team Members")
async def get_deal_team(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        members = await CrmDealTeam.find(
            CrmDealTeam.deal_id == UUID(deal_id),
            CrmDealTeam.tenant_id == tenant_id,
        ).to_list()
        return [_serialize_team_member(m) for m in members]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/team", summary="Add Team Member to Deal", status_code=status.HTTP_201_CREATED)
async def add_deal_team_member(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get("sub"))
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))

        deal = await CrmDeal.find_one(CrmDeal.id == UUID(deal_id), CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        member_user_id = UUID(data["user_id"])

        # Avoid duplicates
        existing = await CrmDealTeam.find_one(
            CrmDealTeam.deal_id == UUID(deal_id),
            CrmDealTeam.user_id == member_user_id,
        )
        if existing:
            raise HTTPException(status_code=409, detail="User already in deal team")

        # Resolve user details
        user_name = data.get("user_name")
        user_email = data.get("user_email")
        if not user_name:
            u = await User.find_one(User.id == member_user_id)
            if u:
                user_name = f"{u.first_name} {u.last_name}".strip()
                user_email = u.email

        try:
            role = DealTeamRole(data.get("role", "sales_owner"))
        except ValueError:
            role = DealTeamRole.sales_owner

        member = CrmDealTeam(
            deal_id=UUID(deal_id),
            tenant_id=tenant_id,
            user_id=member_user_id,
            user_name=user_name,
            user_email=user_email,
            role=role,
            added_by=user_id,
        )
        await member.insert()
        return {"message": "Team member added", "member": _serialize_team_member(member)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{deal_id}/team/{member_id}", summary="Remove Team Member from Deal")
async def remove_deal_team_member(deal_id: str, member_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        member = await CrmDealTeam.find_one(
            CrmDealTeam.id == UUID(member_id),
            CrmDealTeam.deal_id == UUID(deal_id),
            CrmDealTeam.tenant_id == tenant_id,
        )
        if not member:
            raise HTTPException(status_code=404, detail="Team member not found")
        await member.delete()
        return {"message": "Team member removed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Deal Line Items ───────────────────────────────────────────────────────────

@router.get("/{deal_id}/line-items", summary="Get Deal Line Items")
async def get_deal_line_items(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        items = await CrmDealLineItem.find(
            CrmDealLineItem.deal_id == UUID(deal_id),
            CrmDealLineItem.tenant_id == tenant_id,
        ).sort(CrmDealLineItem.sort_order).to_list()

        subtotal = sum((i.quantity * i.unit_price) for i in items)
        total_discount = sum((i.quantity * i.unit_price * i.discount_pct / 100) for i in items)
        total_tax = sum((i.quantity * i.unit_price * (1 - i.discount_pct / 100) * i.tax_pct / 100) for i in items)
        grand_total = sum(i.total for i in items)

        return {
            "items": [_serialize_line_item(i) for i in items],
            "summary": {
                "subtotal": round(subtotal, 2),
                "total_discount": round(total_discount, 2),
                "total_tax": round(total_tax, 2),
                "grand_total": round(grand_total, 2),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/line-items", summary="Add Line Item to Deal", status_code=status.HTTP_201_CREATED)
async def add_deal_line_item(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get("sub"))
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))

        deal = await CrmDeal.find_one(CrmDeal.id == UUID(deal_id), CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        qty = float(data.get("quantity", 1))
        unit_price = float(data.get("unit_price", 0))
        discount_pct = float(data.get("discount_pct", 0))
        tax_pct = float(data.get("tax_pct", 0))

        after_discount = qty * unit_price * (1 - discount_pct / 100)
        total = round(after_discount * (1 + tax_pct / 100), 2)

        # Get next sort order
        existing_count = await CrmDealLineItem.find(CrmDealLineItem.deal_id == UUID(deal_id)).count()

        item = CrmDealLineItem(
            deal_id=UUID(deal_id),
            tenant_id=tenant_id,
            product_name=data.get("product_name", "Product"),
            description=data.get("description"),
            quantity=qty,
            unit_price=unit_price,
            discount_pct=discount_pct,
            tax_pct=tax_pct,
            total=total,
            sort_order=existing_count,
            created_by=user_id,
        )
        await item.insert()
        return {"message": "Line item added", "item": _serialize_line_item(item)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{deal_id}/line-items/{item_id}", summary="Update Deal Line Item")
async def update_deal_line_item(deal_id: str, item_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        item = await CrmDealLineItem.find_one(
            CrmDealLineItem.id == UUID(item_id),
            CrmDealLineItem.deal_id == UUID(deal_id),
            CrmDealLineItem.tenant_id == tenant_id,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Line item not found")

        for field in ("product_name", "description"):
            if field in data:
                setattr(item, field, data[field])

        for num_field in ("quantity", "unit_price", "discount_pct", "tax_pct", "sort_order"):
            if num_field in data:
                setattr(item, num_field, float(data[num_field]))

        # Recalculate total
        after_discount = item.quantity * item.unit_price * (1 - item.discount_pct / 100)
        item.total = round(after_discount * (1 + item.tax_pct / 100), 2)

        from datetime import datetime
        item.updated_at = datetime.utcnow()
        await item.save()
        return {"message": "Line item updated", "item": _serialize_line_item(item)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{deal_id}/line-items/{item_id}", summary="Delete Deal Line Item")
async def delete_deal_line_item(deal_id: str, item_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get("tid") or current_user.get("tenant_id"))
        item = await CrmDealLineItem.find_one(
            CrmDealLineItem.id == UUID(item_id),
            CrmDealLineItem.deal_id == UUID(deal_id),
            CrmDealLineItem.tenant_id == tenant_id,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Line item not found")
        await item.delete()
        return {"message": "Line item deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
