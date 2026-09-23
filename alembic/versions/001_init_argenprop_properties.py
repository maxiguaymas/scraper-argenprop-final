"""init_argenprop_properties

Revision ID: 001_init_ap
Revises: 
Create Date: 2026-09-21 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_init_ap"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "argenprop_properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("argenprop_id", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=True),
        sa.Column("titulo_generado", sa.Text(), nullable=True),
        sa.Column("tipo_propiedad", sa.Text(), nullable=True),
        sa.Column("tipo_operacion", sa.Text(), nullable=True),
        sa.Column("precio", sa.Double(), nullable=True),
        sa.Column("moneda", sa.Text(), nullable=True),
        sa.Column("expensas", sa.Double(), nullable=True),
        sa.Column("expensas_moneda", sa.Text(), nullable=True),
        sa.Column("superficie_total", sa.Double(), nullable=True),
        sa.Column("superficie_cubierta", sa.Double(), nullable=True),
        sa.Column("ambientes", sa.Integer(), nullable=True),
        sa.Column("dormitorios", sa.Integer(), nullable=True),
        sa.Column("banos", sa.Integer(), nullable=True),
        sa.Column("cocheras", sa.Integer(), nullable=True),
        sa.Column("direccion", sa.Text(), nullable=True),
        sa.Column("barrio", sa.Text(), nullable=True),
        sa.Column("ubicacion", sa.Text(), nullable=True),
        sa.Column("localidad", sa.Text(), nullable=False, server_default="Salta"),
        sa.Column("provincia", sa.Text(), nullable=False, server_default="Salta"),
        sa.Column("latitud", sa.Double(), nullable=True),
        sa.Column("longitud", sa.Double(), nullable=True),
        sa.Column("coordenadas_origen", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("imagen_principal", sa.Text(), nullable=True),
        sa.Column("imagenes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("precio_m2", sa.Double(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("anunciante_nombre", sa.Text(), nullable=True),
        sa.Column("anunciante_logo", sa.Text(), nullable=True),
        sa.Column("anunciante_cucis", sa.Text(), nullable=True),
        sa.Column("anunciante_telefono", sa.Text(), nullable=True),
        sa.Column("anunciante_whatsapp", sa.Text(), nullable=True),
        sa.Column("visualizaciones", sa.Integer(), nullable=True),
        sa.Column("publicado_hace", sa.Text(), nullable=True),
        sa.Column("fecha_publicacion", sa.Text(), nullable=True),
        sa.Column("es_super_destacado", sa.Boolean(), nullable=True),
        sa.Column("nivel_destacado", sa.Text(), nullable=True),
        sa.Column("apto_credito", sa.Boolean(), nullable=True),
        sa.Column("a_estrenar", sa.Boolean(), nullable=True),
        sa.Column("pagina_origen", sa.Integer(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=True, server_default="activo"),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("primera_vez_visto", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultima_actualizacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("informacion_ia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_argenprop_properties_argenprop_id", "argenprop_properties", ["argenprop_id"], unique=True)
    op.create_index("ix_argenprop_properties_activa", "argenprop_properties", ["activa"])
    op.create_index("ix_argenprop_properties_tipo_propiedad", "argenprop_properties", ["tipo_propiedad"])
    op.create_index("ix_argenprop_properties_tipo_operacion", "argenprop_properties", ["tipo_operacion"])
    op.create_index("ix_argenprop_properties_localidad", "argenprop_properties", ["localidad"])
    op.create_index("ix_argenprop_properties_barrio", "argenprop_properties", ["barrio"])


def downgrade() -> None:
    op.drop_table("argenprop_properties")
