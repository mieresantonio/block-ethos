"""leccion de muestra: marca is_sample en lessons

Revision ID: a4b7db1a94a9
Revises: 05e61b18b5ea
Create Date: 2026-11-23

Una columna nueva en lessons, segura sobre filas existentes:
is_sample es NOT NULL con server_default false (mismo patrón que
is_profile_public en 05e61b18b5ea): sin el server_default,
SQLite/Postgres rechazarían añadir una columna NOT NULL a una
tabla con filas. Sin unicidad: no hay riesgo de aborto por
duplicados como en la migración 195659629ab0 de certificados.
La semilla (P2) marca la muestra; la migración solo añade la
columna en False.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b7db1a94a9'
down_revision = '05e61b18b5ea'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_sample', sa.Boolean(), server_default=sa.false(),
            nullable=False))


def downgrade():
    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.drop_column('is_sample')
