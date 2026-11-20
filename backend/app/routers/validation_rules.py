from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import SUSTAINABILITY_MANAGER, CurrentUser, Db, require_roles
from app.schemas.validation_rules import ValidationRulesIn, ValidationRulesOut
from app.services import rules_config
from app.services.validation import Limit, ValidationConfig

router = APIRouter(prefix="/validation-rules", tags=["validation rules"])


@router.get("", response_model=ValidationRulesOut, summary="Active data-validation configuration")
def get_rules(db: Db, _: CurrentUser):
    return rules_config.to_dict(rules_config.load(db))


@router.put("", response_model=ValidationRulesOut, summary="Replace the validation configuration")
def put_rules(body: ValidationRulesIn, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))):
    cfg = ValidationConfig(
        spike_enabled=body.spike_enabled, spike_pct=body.spike_pct, high_pct=body.high_pct,
        history_months=body.history_months, spike_block_high=body.spike_block_high,
        zero_enabled=body.zero_enabled, zero_block=body.zero_block,
        limits=tuple(Limit(l.field, l.max, l.enabled, l.block) for l in body.limits),
        inspection_interval_days=body.inspection_interval_days,
    )
    return rules_config.save(db, user, cfg)
