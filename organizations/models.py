"""Stable organization-domain imports.

These models retain the ``housekeeping`` app label for migration and database
compatibility. New code should import organization-owned concepts from this
module; a later data migration can transfer model state without renaming the
existing production tables.
"""

from housekeeping.models import (
    Area,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    BranchOwnershipHistory,
    HousekeepingTeam,
    Room,
    Shift,
    ShiftAssignment,
    Skill,
)

__all__ = [
    "Area",
    "Branch",
    "BranchHousekeepingPolicy",
    "BranchMembership",
    "BranchOwnershipHistory",
    "HousekeepingTeam",
    "Room",
    "Shift",
    "ShiftAssignment",
    "Skill",
]
