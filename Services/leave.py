from Models import leave
from datetime import datetime

class LeavePolicyService:

    @staticmethod
    async def create_policy(db, data):
        policy = leave(data.dict())
        await db.leave_policies.insert_one(policy)
        return policy

    @staticmethod
    async def get_policies(db):
        policies = []
        async for policy in db.leave_policies.find():
            policy["id"] = policy["_id"]
            policies.append(policy)
        return policies

    @staticmethod
    async def get_policy_by_id(db, policy_id: str):
        policy = await db.leave_policies.find_one({"_id": policy_id})
        if policy:
            policy["id"] = policy["_id"]
        return policy

    @staticmethod
    async def update_policy(db, policy_id: str, data):
        update_data = {k: v for k, v in data.dict().items() if v is not None}
        await db.leave_policies.update_one(
            {"_id": policy_id},
            {"$set": update_data}
        )
        return await LeavePolicyService.get_policy_by_id(db, policy_id)

    @staticmethod
    async def delete_policy(db, policy_id: str):
        await db.leave_policies.delete_one({"_id": policy_id})
        return {"message": "Deleted successfully"}