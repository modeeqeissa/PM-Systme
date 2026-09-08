import datetime as dt
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Person(Base):
    """persons — migration 0004 / docs Section 9.3.2.

    The master record for a non-officer individual encountered in cases
    (suspect, victim, witness). `arrests.suspect_id` and `statements.person_id`
    reference this row; `case_persons` links a person to a case with a role.
    """

    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date)
    # UNIQUE where present — the practical de-duplication key (docs §9.3.2).
    national_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    gender: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CasePerson(Base):
    """case_persons — migration 0004 / docs Section 9.3.2.

    A person's role in one specific case. The same person may hold different
    roles across different cases (and, rarely, two roles in one case — a suspect
    who later gives a witness statement); `uq_case_persons_case_person_role`
    only forbids the exact same (case, person, role) twice.
    """

    __tablename__ = "case_persons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
