import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class TestUserDefaults:
    async def test_id_assigned_on_create(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert isinstance(user.id, uuid.UUID)

    async def test_is_admin_defaults_false(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.is_admin is False

    async def test_is_active_defaults_true(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.is_active is True

    async def test_theme_defaults_light(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.theme == "light"

    async def test_measurement_system_defaults_metric(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.measurement_system == "metric"

    async def test_ai_training_consent_defaults_true(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.ai_training_consent is True

    async def test_timestamps_set_on_create(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.created_at is not None
        assert user.updated_at is not None

    async def test_deleted_at_none_by_default(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.deleted_at is None
        assert user.is_deleted is False


class TestUserSoftDelete:
    async def test_soft_delete_sets_deleted_at(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        user.soft_delete()
        assert user.deleted_at is not None

    async def test_soft_delete_sets_is_deleted(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        user.soft_delete()
        assert user.is_deleted is True

    async def test_soft_delete_persists(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        user.soft_delete()
        await db_session.commit()
        await db_session.refresh(user)
        assert user.is_deleted is True


class TestUserFields:
    async def test_email_stored(self, db_session: AsyncSession):
        user = User(email="custom@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.email == "custom@example.com"

    async def test_display_name_stored(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="Alice", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.display_name == "Alice"

    async def test_oidc_sub_stored(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="my-unique-sub")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.oidc_sub == "my-unique-sub"

    async def test_admin_flag_stored(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001", is_admin=True)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.is_admin is True


class TestUserDeletionFields:
    async def test_deletion_state_defaults_none(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.deletion_state is None

    async def test_deletion_initiated_at_defaults_none(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        assert user.deletion_initiated_at is None

    async def test_deletion_state_persists(self, db_session: AsyncSession):
        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        user.deletion_state = "pending"
        await db_session.commit()
        await db_session.refresh(user)
        assert user.deletion_state == "pending"

    async def test_deletion_initiated_at_persists(self, db_session: AsyncSession):
        from datetime import datetime, timezone

        user = User(email="u@example.com", display_name="U", oidc_sub="sub-001")
        db_session.add(user)
        await db_session.commit()
        now = datetime.now(timezone.utc)
        user.deletion_initiated_at = now
        await db_session.commit()
        await db_session.refresh(user)
        assert user.deletion_initiated_at is not None
