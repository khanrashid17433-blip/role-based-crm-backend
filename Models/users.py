
class User(Document):
    name: str
    email: EmailStr
    role: str = "employee"
    is_active: bool = True
    created_at: datetime = datetime.utcnow()

    class Settings:
        name = "users"