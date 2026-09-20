"""Новый старт (НАЧАТЬ, фото, документы по ссылкам) и раздел услуг натальной карты.

Только данные, схема не меняется:
- сбрасываются сохранённые в админке приветствие и текст согласия, чтобы вступили
  в силу новые тексты по умолчанию; удаляются кнопки меню «Условия»/«Политика»;
- прежняя услуга «Натальная карта» (code=natal) становится «Полным анализом личности»,
  если её название не меняли в админке. Остальные услуги раздела добавляет scripts.seed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_TITLE = "🌟 Полный анализ личности по вашей дате рождения"
NEW_DESCRIPTION = (
    "Ваш характер, эмоции, сильные стороны и привычные реакции в отношениях — в одном "
    "подробном астрологическом разборе. Возможность посмотреть на себя со стороны и "
    "заметить качества, которым вы раньше не придавали значения."
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM settings WHERE key IN "
        "('welcome_text', 'consent_text', 'btn_terms', 'btn_privacy')"
    ))
    bind.execute(
        sa.text(
            "UPDATE services SET title = :title, description = :description, sort_order = 55 "
            "WHERE code = 'natal' AND title = 'Натальная карта'"
        ),
        {"title": NEW_TITLE, "description": NEW_DESCRIPTION},
    )


def downgrade() -> None:
    pass  # прежние тексты не восстанавливаются
