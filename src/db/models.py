from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Double, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ArgenpropProperty(Base):
    __tablename__ = "argenprop_properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    argenprop_id: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )

    titulo: Mapped[str | None] = mapped_column(Text, nullable=True)
    titulo_generado: Mapped[str | None] = mapped_column(Text, nullable=True)

    tipo_propiedad: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    tipo_operacion: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    precio: Mapped[float | None] = mapped_column(Double, nullable=True)
    moneda: Mapped[str | None] = mapped_column(Text, nullable=True)

    expensas: Mapped[float | None] = mapped_column(Double, nullable=True)
    expensas_moneda: Mapped[str | None] = mapped_column(Text, nullable=True)

    superficie_total: Mapped[float | None] = mapped_column(Double, nullable=True)
    superficie_cubierta: Mapped[float | None] = mapped_column(Double, nullable=True)

    ambientes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dormitorios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    banos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cocheras: Mapped[int | None] = mapped_column(Integer, nullable=True)

    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    barrio: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    ubicacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    localidad: Mapped[str] = mapped_column(
        Text, nullable=False, default="Salta", index=True
    )
    provincia: Mapped[str] = mapped_column(
        Text, nullable=False, default="Salta"
    )

    latitud: Mapped[float | None] = mapped_column(Double, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Double, nullable=True)
    coordenadas_origen: Mapped[str | None] = mapped_column(Text, nullable=True)

    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    imagen_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    imagenes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    precio_m2: Mapped[float | None] = mapped_column(Double, nullable=True)

    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    anunciante_nombre: Mapped[str | None] = mapped_column(Text, nullable=True)
    anunciante_logo: Mapped[str | None] = mapped_column(Text, nullable=True)
    anunciante_cucis: Mapped[str | None] = mapped_column(Text, nullable=True)
    anunciante_telefono: Mapped[str | None] = mapped_column(Text, nullable=True)
    anunciante_whatsapp: Mapped[str | None] = mapped_column(Text, nullable=True)

    visualizaciones: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publicado_hace: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_publicacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    es_super_destacado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    nivel_destacado: Mapped[str | None] = mapped_column(Text, nullable=True)
    apto_credito: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    a_estrenar: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pagina_origen: Mapped[int | None] = mapped_column(Integer, nullable=True)

    estado: Mapped[str | None] = mapped_column(Text, nullable=True, default="activo")

    features: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    primera_vez_visto: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ultima_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    informacion_ia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
