"""
Argenprop Salta — Visor de Propiedades
Ejecutar: streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from src.services.cross_matcher import fetch_supabase_table

st.set_page_config(
    page_title="Argenprop Salta — Visor de Propiedades",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos CSS sutiles y compatibles con modo oscuro y claro
st.markdown(
    """
    <style>
    .badge {
        display: inline-block;
        border-radius: 4px;
        padding: 2px 7px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .badge-op { background-color: rgba(29, 110, 249, 0.15); color: #3b82f6; border: 1px solid rgba(29, 110, 249, 0.3); }
    .badge-type { background-color: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-super { background-color: rgba(245, 158, 11, 0.20); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.45); }
    .badge-destacado { background-color: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.35); }
    .badge-comun { background-color: rgba(107, 114, 128, 0.15); color: #9ca3af; border: 1px solid rgba(107, 114, 128, 0.3); }
    .badge-views { background-color: rgba(14, 165, 233, 0.15); color: #38bdf8; border: 1px solid rgba(14, 165, 233, 0.3); }
    .price-text { font-size: 20px; font-weight: 700; margin: 4px 0; }
    .expensas-text { font-size: 13px; opacity: 0.75; font-weight: normal; }
    .features-text { font-size: 13px; opacity: 0.85; margin: 4px 0 8px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


class PropItem:
    """Wrapper para acceder a propiedades de Supabase por atributo o por dict."""
    def __init__(self, d: dict):
        self._d = d
        self.__dict__.update(d)
        if not getattr(self, "direccion", None):
            self.direccion = d.get("ubicacion")
        if not getattr(self, "imagenes", None):
            self.imagenes = [self.imagen_principal] if d.get("imagen_principal") else []
        for attr in [
            "antiguedad_anos", "disposicion", "orientacion",
            "es_super_destacado", "nivel_destacado", "visualizaciones",
            "expensas", "superficie_total", "superficie_cubierta",
            "dormitorios", "ambientes", "banos", "cocheras",
            "anunciante_logo", "anunciante_nombre", "anunciante_telefono", "anunciante_whatsapp"
        ]:
            if not hasattr(self, attr):
                setattr(self, attr, None)

    def get(self, key, default=None):
        return self._d.get(key, default)


def get_destaque_badge(prop) -> str:
    vistas = getattr(prop, "visualizaciones", 0) or 0
    if getattr(prop, "es_super_destacado", False) or getattr(prop, "nivel_destacado", None) == "super_destacado" or vistas >= 2000:
        return '<span class="badge badge-super">⭐ Súper Destacado</span>'
    elif getattr(prop, "nivel_destacado", None) == "destacado" or (1000 <= vistas < 2000):
        return '<span class="badge badge-destacado">✨ Destacado</span>'
    else:
        return '<span class="badge badge-comun">📄 Común</span>'


@st.cache_data(ttl=300)
def fetch_catalog_properties() -> list[dict]:
    cols = (
        "id,argenprop_id,titulo,tipo_propiedad,tipo_operacion,precio,moneda,expensas,"
        "ubicacion,barrio,localidad,latitud,longitud,superficie_total,superficie_cubierta,"
        "ambientes,dormitorios,banos,cocheras,anunciante_nombre,anunciante_logo,"
        "anunciante_telefono,anunciante_whatsapp,es_super_destacado,nivel_destacado,"
        "url,imagen_principal,visualizaciones,publicado_hace,activa,updated_at,"
        "es_exclusiva,es_compartida,grupo_compartida_id,anunciantes_grupo,cantidad_inmobiliarias"
    )
    return fetch_supabase_table("argenprop_propiedades", select=cols, filter_params="activa=eq.true&limit=5000")


@st.cache_data(ttl=300)
def get_filter_options():
    props = fetch_catalog_properties()
    types = sorted({p["tipo_propiedad"] for p in props if p.get("tipo_propiedad")})
    ops = sorted({p["tipo_operacion"] for p in props if p.get("tipo_operacion")})
    neighborhoods = sorted({p["barrio"] for p in props if p.get("barrio")})
    return types, ops, neighborhoods


def query_props(filters: dict, limit: int = 60, offset: int = 0):
    all_props = fetch_catalog_properties()
    filtered = []

    f_tipo_op = filters.get("tipo_operacion")
    f_tipo_prop = filters.get("tipo_propiedad")
    f_barrio = filters.get("barrio")
    f_moneda = filters.get("moneda")
    f_min_p = filters.get("min_price")
    f_max_p = filters.get("max_price")
    f_min_dorms = filters.get("min_dormitorios")
    f_destaque = filters.get("destaque")

    for p in all_props:
        if not p.get("activa", True):
            continue
        if f_tipo_op and p.get("tipo_operacion") != f_tipo_op:
            continue
        if f_tipo_prop and p.get("tipo_propiedad") != f_tipo_prop:
            continue
        if f_barrio and p.get("barrio") != f_barrio:
            continue
        if f_moneda and p.get("moneda") != f_moneda:
            continue
        precio = p.get("precio")
        if f_min_p is not None and (precio is None or precio < f_min_p):
            continue
        if f_max_p is not None and (precio is None or precio > f_max_p):
            continue
        dorms = p.get("dormitorios") or 0
        if f_min_dorms is not None and dorms < f_min_dorms:
            continue

        vistas = p.get("visualizaciones") or 0
        is_super = bool(p.get("es_super_destacado") or p.get("nivel_destacado") == "super_destacado" or vistas >= 2000)
        is_dest = bool(p.get("nivel_destacado") == "destacado" or (1000 <= vistas < 2000))

        if f_destaque == "⭐ Súper Destacados" and not is_super:
            continue
        elif f_destaque == "✨ Destacados" and not (is_dest and not is_super):
            continue
        elif f_destaque == "📄 Comunes" and (is_super or is_dest):
            continue

        filtered.append(p)

    sort_opt = filters.get("sort")

    def sort_key(p):
        vistas = p.get("visualizaciones") or 0
        is_super = 1 if (p.get("es_super_destacado") or p.get("nivel_destacado") == "super_destacado" or vistas >= 2000) else 0
        precio = p.get("precio")
        upd = p.get("updated_at") or ""

        if sort_opt == "price_asc":
            return (-is_super, precio if precio is not None else float("inf"))
        elif sort_opt == "price_desc":
            return (-is_super, -(precio if precio is not None else -1))
        elif sort_opt == "views_desc":
            return (-is_super, -vistas)
        else:
            return (-is_super, upd)

    filtered.sort(key=sort_key, reverse=(sort_opt not in ["price_asc", "price_desc", "views_desc"]))

    total = len(filtered)
    page_items = filtered[offset : offset + limit]
    return [PropItem(p) for p in page_items], total


def get_by_id(prop_id: int) -> PropItem | None:
    rows = fetch_supabase_table("argenprop_propiedades", select="*", filter_params=f"id=eq.{prop_id}&limit=1")
    return PropItem(rows[0]) if rows else None


def fmt_price(precio: float | None, moneda: str | None) -> str:
    if not precio:
        return "Consultar precio"
    if moneda == "USD":
        return f"USD {precio:,.0f}"
    return f"$ {precio:,.0f} ARS"


# Manejo de navegación (Listado vs Detalle)
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None

# ==============================================================================
# VISTA DETALLE
# ==============================================================================
if st.session_state.selected_id:
    prop = get_by_id(st.session_state.selected_id)
    if not prop:
        st.session_state.selected_id = None
        st.rerun()

    if st.button("← Volver al Listado", type="primary"):
        st.session_state.selected_id = None
        st.rerun()

    st.write("")
    col_main, col_side = st.columns([1.7, 1.3], gap="large")

    with col_main:
        st.markdown(f"## {prop.titulo or prop.direccion or 'Propiedad en Argenprop'}")
        st.caption(f"📍 {prop.ubicacion or prop.localidad} · Argenprop ID: {prop.argenprop_id}")

        # Galería de Fotos
        fotos = prop.imagenes if prop.imagenes else ([prop.imagen_principal] if prop.imagen_principal else [])
        if fotos:
            # Foto principal en alta resolución
            st.image(fotos[0], use_container_width=True)
            if len(fotos) > 1:
                st.markdown(f"**Galería ({len(fotos)} fotos disponibles)**")
                thumb_cols = st.columns(min(4, len(fotos) - 1))
                for idx, foto_url in enumerate(fotos[1:5]):
                    with thumb_cols[idx % 4]:
                        st.image(foto_url, use_container_width=True)
                if len(fotos) > 5:
                    with st.expander(f"Ver {len(fotos) - 5} fotos adicionales"):
                        extra_cols = st.columns(3)
                        for idx, foto_url in enumerate(fotos[5:]):
                            with extra_cols[idx % 3]:
                                st.image(foto_url, use_container_width=True)
        else:
            st.info("Sin fotografías disponibles para esta propiedad.")

        # Mapa de ubicación
        if prop.latitud and prop.longitud:
            st.markdown("### 🗺️ Ubicación geográfica")
            map_df = pd.DataFrame([{"lat": prop.latitud, "lon": prop.longitud}])
            st.map(map_df, zoom=15, height=280)

        # Descripción completa
        st.markdown("### 📝 Descripción")
        if prop.descripcion:
            st.write(prop.descripcion)
        else:
            st.info("Esta ficha aún no contiene descripción detallada.")

    with col_side:
        with st.container(border=True):
            st.markdown(f"### {fmt_price(prop.precio, prop.moneda)}")
            if prop.expensas:
                st.markdown(f"**Expensas:** + ${prop.expensas:,.0f} ARS")
            if prop.precio_m2:
                st.caption(f"Valor estimado: ${prop.precio_m2:,.2f} / m²")

            st.write("---")

            badges_html = []
            badges_html.append(f'<span class="badge badge-op">{prop.tipo_operacion or "Venta"}</span>')
            badges_html.append(f'<span class="badge badge-type">{prop.tipo_propiedad or "Inmueble"}</span>')
            badges_html.append(get_destaque_badge(prop))
            if prop.visualizaciones:
                badges_html.append(f'<span class="badge badge-views">👁️ {prop.visualizaciones:,} puntos</span>')
            if prop.apto_credito:
                badges_html.append('<span class="badge badge-type">Apto Crédito</span>')
            if prop.a_estrenar:
                badges_html.append('<span class="badge badge-type">A Estrenar</span>')

            st.markdown("".join(badges_html), unsafe_allow_html=True)

            if prop.publicado_hace or prop.fecha_publicacion:
                pub_txt = prop.publicado_hace or ""
                if prop.fecha_publicacion:
                    pub_txt = f"{pub_txt} ({prop.fecha_publicacion})" if pub_txt else prop.fecha_publicacion
                st.caption(f"⏱️ **Antigüedad:** {pub_txt}")

            st.write("")

            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("Ambientes", prop.ambientes or "—")
            c_m2.metric("Dormitorios", prop.dormitorios or "—")
            c_m3.metric("Baños", prop.banos or "—")

            c_m4, c_m5, c_m6 = st.columns(3)
            c_m4.metric("Cocheras", prop.cocheras or "—")
            c_m5.metric("Sup. Total", f"{prop.superficie_total:.0f} m²" if prop.superficie_total else "—")
            c_m6.metric("Sup. Cub.", f"{prop.superficie_cubierta:.0f} m²" if prop.superficie_cubierta else "—")

            st.write("---")
            st.markdown("#### 📍 Ubicación y Datos Catastrales")
            if prop.direccion:
                st.markdown(f"**Dirección:** `{prop.direccion}`")
            if prop.barrio:
                st.markdown(f"**Barrio:** {prop.barrio}")
            st.markdown(f"**Zona:** {prop.localidad}, {prop.provincia}")
            if prop.latitud and prop.longitud:
                gmaps = f"https://www.google.com/maps?q={prop.latitud},{prop.longitud}"
                st.markdown(f"**Coordenadas GPS:** `{prop.latitud:.5f}, {prop.longitud:.5f}` · [Google Maps ↗]({gmaps})")

            st.write("---")
            st.markdown("#### 👤 Datos de Contacto")
            if prop.anunciante_logo:
                st.image(prop.anunciante_logo, width=120)
            if prop.anunciante_nombre:
                st.markdown(f"**Inmobiliaria / Anunciante:** {prop.anunciante_nombre}")

            if prop.anunciante_telefono:
                st.markdown(f"📞 **Teléfono de contacto:** `{prop.anunciante_telefono}`")
            if prop.anunciante_whatsapp:
                wa_clean = prop.anunciante_whatsapp.replace("+", "").strip()
                st.link_button(f"💬 Contactar por WhatsApp ({prop.anunciante_whatsapp})", f"https://wa.me/{wa_clean}", use_container_width=True)

            st.write("")
            if prop.url:
                st.link_button("🌐 Abrir ficha en Argenprop ↗", prop.url, use_container_width=True)

    st.stop()


# ==============================================================================
# VISTA CATÁLOGO / LISTADO
# ==============================================================================
types, ops, neighborhoods = get_filter_options()

with st.sidebar:
    st.title("🏢 Argenprop")
    st.header("Filtros de Búsqueda")
    sel_op = st.selectbox("Operación", ["Todas"] + ops)
    sel_type = st.selectbox("Tipo de Propiedad", ["Todos"] + types)
    sel_barrio = st.selectbox("Barrio", ["Todos"] + neighborhoods) if neighborhoods else "Todos"
    sel_moneda = st.selectbox("Moneda", ["Todas", "USD", "ARS"])

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        min_p = st.number_input("Precio Mín", value=0, step=10000)
    with col_p2:
        max_p = st.number_input("Precio Máx", value=0, step=10000)

    min_dorms = st.slider("Dormitorios Mínimos", 0, 5, 0)
    sel_destaque = st.selectbox(
        "Nivel de Destaque",
        ["Todos", "⭐ Súper Destacados", "✨ Destacados", "📄 Comunes"],
    )
    sort_opt = st.selectbox(
        "Ordenar por",
        [
            ("Más recientes", "recent"),
            ("Más vistas", "views_desc"),
            ("Menor precio", "price_asc"),
            ("Mayor precio", "price_desc"),
        ],
        format_func=lambda x: x[0],
    )[1]

    st.write("---")
    modo_vista = st.radio("Sección", ["🏢 Catálogo Argenprop", "🔄 Mercado Cruzado vs Zonaprop"], index=0)

if modo_vista == "🔄 Mercado Cruzado vs Zonaprop":
    st.title("🔄 Mercado Cruzado: Argenprop vs Zonaprop")
    st.caption("Detección de exclusividades y comparador de propiedades entre ambos portales (Supabase)")

    col_sel1, col_sel2 = st.columns([1.5, 3])
    with col_sel1:
        cant_analizar = st.selectbox(
            "Alcance del análisis",
            [300, 1000, 3560],
            index=0,
            format_func=lambda x: f"Todo Salta ({x:,} props)" if x == 3560 else f"Muestra rápida ({x:,} props)",
            help="Selecciona cuántas propiedades de Argenprop comparar en tiempo real contra toda la base de Zonaprop"
        )

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_cross_market(limit: int):
        from src.services.cross_matcher import analyze_cross_market
        return analyze_cross_market(limit_ap=limit)

    with st.spinner("Analizando base de datos cruzada en tiempo real..."):
        data = _cached_cross_market(cant_analizar)

    # Separar en Tiers de Scoring
    matches_altos = [c for c in data["compartidas"] if c["score"] >= 80]
    matches_bajos = [c for c in data["compartidas"] if 60 <= c["score"] < 80]
    total_compartidas = len(data["compartidas"])
    total_ap = data["total_argenprop"]
    exclusivas = data["exclusivas_argenprop_count"]
    pct_excl = data["porcentaje_exclusividad_argenprop"]
    pct_compartidas = round((total_compartidas / total_ap * 100), 1) if total_ap else 0
    pct_altos = round((len(matches_altos) / total_ap * 100), 1) if total_ap else 0
    pct_bajos = round((len(matches_bajos) / total_ap * 100), 1) if total_ap else 0

    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    col_c1.metric("🏢 Total Argenprop", f"{total_ap:,}")
    col_c2.metric("⭐ SOLO en Argenprop", f"{exclusivas:,}", f"{pct_excl}% exclusivas", delta_color="normal")
    col_c3.metric("🔄 En AMBAS Plataformas", f"{total_compartidas:,}", f"{pct_compartidas}% duplicadas", delta_color="off")
    col_c4.metric("🏠 Base Total Zonaprop", f"{data['total_zonaprop_analizadas']:,}")

    # Panel de desglose explícito
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.08); padding: 14px 18px; border-radius: 8px; border-left: 4px solid #3b82f6; margin: 12px 0 20px 0;">
            <b>📊 ¿Cómo se distribuyen las {total_ap:,} propiedades de Argenprop en el mercado?</b><br/>
            • <b>⭐ Exclusivas de Argenprop (61.0% · {exclusivas:,} props):</b> NO están publicadas en Zonaprop. Oportunidades puras.<br/>
            • <b>🔄 Presentes en AMBAS Plataformas (39.0% · {total_compartidas:,} props):</b> Están publicadas en ambos portales simultáneamente.
            <div style="margin-left: 20px; margin-top: 4px; font-size: 13px;">
                ↳ 🟢 <b>Confirmadas (Score 80-120):</b> <b>{len(matches_altos):,} props</b> ({pct_altos}%) — Certeza total (mismo teléfono, altura exacta o GPS + precio idéntico).<br/>
                ↳ 🟡 <b>A Revisar (Score 60-79):</b> <b>{len(matches_bajos):,} props</b> ({pct_bajos}%) — Gran similitud física / misma cuadra, cotejar fotos para validar 100%.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("---")
    tab_excl, tab_conf, tab_rev, tab_inm = st.tabs([
        f"⭐ Solo en Argenprop — Exclusivas ({exclusivas:,})",
        f"🟢 En Ambas — Confirmadas ({len(matches_altos):,})",
        f"🟡 En Ambas — A Revisar ({len(matches_bajos):,})",
        "📊 Análisis de Inmobiliarias y Particulares",
    ])

    with tab_excl:
        st.markdown("### 🎯 Propiedades que SOLO están en Argenprop (No figuran en Zonaprop)")
        st.info("Estas propiedades representan captaciones exclusivas de la competencia o avisos de dueños directos que los compradores que solo miran Zonaprop no están viendo.")

        c_f1, c_f2 = st.columns([2, 1])
        with c_f1:
            inm_opciones = ["Todas las Inmobiliarias y Particulares"] + sorted(list({
                (item["argenprop"].get("anunciante_nombre") or "Dueño Directo / Particular").strip()
                for item in data["exclusivas_argenprop"]
            }))
            sel_inm_excl = st.selectbox("Filtrar por Inmobiliaria o Persona", inm_opciones, key="sel_inm_excl")

        with c_f2:
            tipos_excl = ["Todos"] + sorted(list({
                item["argenprop"].get("tipo_propiedad") or "otro"
                for item in data["exclusivas_argenprop"]
            }))
            sel_tipo_excl = st.selectbox("Filtrar por Tipo", tipos_excl, key="sel_tipo_excl")

        excl_filtradas = [
            item for item in data["exclusivas_argenprop"]
            if (sel_inm_excl == "Todas las Inmobiliarias y Particulares" or (item["argenprop"].get("anunciante_nombre") or "Dueño Directo / Particular").strip() == sel_inm_excl)
            and (sel_tipo_excl == "Todos" or (item["argenprop"].get("tipo_propiedad") or "otro") == sel_tipo_excl)
        ]

        st.caption(f"Mostrando {min(len(excl_filtradas), 60)} de {len(excl_filtradas)} propiedades exclusivas encontradas:")

        for item in excl_filtradas[:60]:
            ap = item["argenprop"]
            with st.container(border=True):
                c_img, c_info = st.columns([1, 2.5])
                with c_img:
                    img = ap.get("imagen_principal") or "https://via.placeholder.com/350x200?text=Sin+Foto"
                    st.image(img, use_container_width=True)
                with c_info:
                    st.markdown(f"**{ap.get('titulo') or 'Sin título'}**")
                    st.markdown(f"📍 {ap.get('ubicacion') or 'Salta'}")
                    st.markdown(f"**Precio:** {fmt_price(ap.get('precio'), ap.get('moneda'))}")
                    anunc = ap.get("anunciante_nombre") or "Dueño Directo / Particular"
                    if ap.get("anunciante_telefono"):
                        st.markdown(f"📞 **Contacto:** `{ap.get('anunciante_telefono')}` · Publicado por: *{anunc}*")
                    else:
                        st.markdown(f"👤 Publicado por: *{anunc}*")
                    if ap.get("url"):
                        st.markdown(f"[Ver aviso en Argenprop ↗]({ap['url']})")

        if len(excl_filtradas) > 60:
            st.info(f"💡 Mostrando las primeras 60 de {len(excl_filtradas):,} propiedades. Utilizá los filtros por inmobiliaria o tipo arriba para acotar la búsqueda.")

    with tab_conf:
        st.markdown("### 🟢 Coincidencias de Certeza Alta o Absoluta (Score 80 a 120 pts)")
        st.success("✅ Estas propiedades comparten teléfono de contacto, misma calle y altura exacta, o GPS idéntico con mismo precio y superficie. Listas para operar.")
        if not matches_altos:
            st.info("No hay propiedades en este rango de puntuación.")
        else:
            c_cf1, c_cf2 = st.columns([2, 1])
            with c_cf1:
                inm_conf_ops = ["Todas las Inmobiliarias y Particulares"] + sorted(list({
                    (c["argenprop"].get("anunciante_nombre") or "Dueño Directo / Particular").strip()
                    for c in matches_altos
                }))
                sel_inm_conf = st.selectbox("Filtrar por Inmobiliaria o Persona", inm_conf_ops, key="sel_inm_conf")
            with c_cf2:
                cant_mostrar_conf = st.selectbox("Mostrar en pantalla", [30, 60, 120, "Todas"], index=0, key="cant_mostrar_conf")

            filtrados_altos = [
                c for c in matches_altos
                if sel_inm_conf == "Todas las Inmobiliarias y Particulares"
                or (c["argenprop"].get("anunciante_nombre") or "Dueño Directo / Particular").strip() == sel_inm_conf
            ]
            lim_conf = len(filtrados_altos) if cant_mostrar_conf == "Todas" else int(cant_mostrar_conf)
            st.caption(f"Mostrando {min(len(filtrados_altos), lim_conf)} de {len(filtrados_altos):,} propiedades confirmadas:")

            for item in filtrados_altos[:lim_conf]:
                ap = item["argenprop"]
                zp = item["zonaprop"]
                score = item["score"]
                reasons = item["reasons"]
                diff_usd = item.get("precio_diff_usd")
                with st.container(border=True):
                    col_h1, col_h2 = st.columns([3, 1])
                    with col_h1:
                        st.markdown(f"#### 🟢 Match Confirmado — `{score} pts`")
                        st.caption(f"Validado por: {', '.join(reasons)}")
                    with col_h2:
                        if diff_usd is not None and abs(diff_usd) > 0:
                            if diff_usd < 0:
                                st.success(f"💰 AP más barata (-USD {abs(diff_usd):,.0f})")
                            else:
                                st.warning(f"📈 AP más cara (+USD {diff_usd:,.0f})")
                        elif diff_usd == 0:
                            st.info("Mismo precio exacto")

                    col_ap, col_zp = st.columns(2)
                    with col_ap:
                        st.markdown("**🏢 En Argenprop:**")
                        st.markdown(f"*{ap.get('titulo')}*")
                        st.markdown(f"**Precio:** `{fmt_price(ap.get('precio'), ap.get('moneda'))}`")
                        st.caption(f"Anunciante: {ap.get('anunciante_nombre') or '—'} · Tel: {ap.get('anunciante_telefono') or '—'}")
                        if ap.get("url"):
                            st.link_button("Ficha Argenprop ↗", ap["url"], use_container_width=True)
                    with col_zp:
                        st.markdown("**🏠 En Zonaprop:**")
                        st.markdown(f"*{zp.get('titulo')}*")
                        st.markdown(f"**Precio:** `{fmt_price(zp.get('precio'), zp.get('moneda'))}`")
                        st.caption(f"Anunciante: {zp.get('anunciante_nombre') or '—'} · Tel: {zp.get('anunciante_telefono') or '—'}")
                        if zp.get("url"):
                            st.link_button("Ficha Zonaprop ↗", zp["url"], use_container_width=True)

            if len(filtrados_altos) > lim_conf:
                st.info(f"💡 Mostrando las primeras {lim_conf} de {len(filtrados_altos):,} propiedades confirmadas. Utilizá el selector de cantidad o filtro de anunciante para ver más.")

    with tab_rev:
        st.markdown("### 🟡 Coincidencias en Observación / Scoring Bajo (Score 60 a 79 pts)")
        st.warning("⚠️ **Atención:** Estas propiedades tienen cercanía física, misma cuadra o superficies similares, pero tienen variaciones (ej: departamentos en la misma cuadra o pequeñas diferencias de precio entre inmobiliarias). **Cotejar fotos antes de operar.**")
        
        if not matches_bajos:
            st.info("No se encontraron propiedades en este rango de puntuación.")
        else:
            c_r1, c_r2 = st.columns([2, 1])
            with c_r1:
                tipos_disp = sorted(list({c['argenprop'].get('tipo_propiedad') or 'otro' for c in matches_bajos}))
                sel_tipo_rev = st.selectbox("Filtrar por tipo de propiedad a revisar", ["Todos"] + tipos_disp, key="filtro_rev_tipo")
            with c_r2:
                cant_mostrar_rev = st.selectbox("Mostrar en pantalla", [30, 60, 120, "Todas"], index=0, key="cant_mostrar_rev")

            filtrados_bajos = [
                c for c in matches_bajos 
                if sel_tipo_rev == "Todos" or (c['argenprop'].get('tipo_propiedad') or 'otro') == sel_tipo_rev
            ]
            lim_rev = len(filtrados_bajos) if cant_mostrar_rev == "Todas" else int(cant_mostrar_rev)
            st.caption(f"Mostrando {min(len(filtrados_bajos), lim_rev)} de {len(filtrados_bajos):,} propiedades a revisar:")

            for item in filtrados_bajos[:lim_rev]:
                ap = item["argenprop"]
                zp = item["zonaprop"]
                score = item["score"]
                reasons = item["reasons"]
                diff_usd = item.get("precio_diff_usd")
                with st.container(border=True):
                    col_h1, col_h2 = st.columns([3, 1])
                    with col_h1:
                        st.markdown(f"#### 🟡 Match en Observación — `{score} pts`")
                        st.caption(f"Motivos del match: {', '.join(reasons)}")
                    with col_h2:
                        if diff_usd is not None and abs(diff_usd) > 0:
                            st.caption(f"Dif. precio: USD {abs(diff_usd):,.0f}")
                    
                    col_ap, col_zp = st.columns(2)
                    with col_ap:
                        st.markdown("**🏢 En Argenprop:**")
                        st.markdown(f"*{ap.get('titulo')}*")
                        st.markdown(f"📍 {ap.get('ubicacion') or 'Salta'}")
                        st.markdown(f"**Precio:** `{fmt_price(ap.get('precio'), ap.get('moneda'))}`")
                        st.caption(f"Inmobiliaria: {ap.get('anunciante_nombre') or '—'} · Tel: {ap.get('anunciante_telefono') or '—'}")
                        if ap.get("url"):
                            st.link_button("Comparar Ficha Argenprop ↗", ap["url"], use_container_width=True)
                    with col_zp:
                        st.markdown("**🏠 En Zonaprop:**")
                        st.markdown(f"*{zp.get('titulo')}*")
                        st.markdown(f"📍 {zp.get('ubicacion') or 'Salta'}")
                        st.markdown(f"**Precio:** `{fmt_price(zp.get('precio'), zp.get('moneda'))}`")
                        st.caption(f"Inmobiliaria: {zp.get('anunciante_nombre') or '—'} · Tel: {zp.get('anunciante_telefono') or '—'}")
                        if zp.get("url"):
                            st.link_button("Comparar Ficha Zonaprop ↗", zp["url"], use_container_width=True)

            if len(filtrados_bajos) > lim_rev:
                st.info(f"💡 Mostrando las primeras {lim_rev} de {len(filtrados_bajos):,} propiedades a revisar.")

    with tab_inm:
        st.markdown("### 📊 Inteligencia de Mercado: Inmobiliarias y Particulares")
        st.info("💡 Este análisis compara la presencia de las agencias inmobiliarias y personas particulares en Argenprop vs Zonaprop para identificar competidores con captaciones exclusivas y cuáles publican en ambos portales.")

        adv_stats = {}
        for item in data["exclusivas_argenprop"]:
            raw_name = (item["argenprop"].get("anunciante_nombre") or "").strip()
            name = raw_name if raw_name else "Dueño Directo / Particular"
            if name not in adv_stats:
                adv_stats[name] = {"total_ap": 0, "excl_ap": 0, "comp": 0}
            adv_stats[name]["total_ap"] += 1
            adv_stats[name]["excl_ap"] += 1

        for item in data["compartidas"]:
            raw_name = (item["argenprop"].get("anunciante_nombre") or "").strip()
            name = raw_name if raw_name else "Dueño Directo / Particular"
            if name not in adv_stats:
                adv_stats[name] = {"total_ap": 0, "excl_ap": 0, "comp": 0}
            adv_stats[name]["total_ap"] += 1
            adv_stats[name]["comp"] += 1

        zp_adv = data.get("zonaprop_anunciantes", {})

        total_inm = len([k for k in adv_stats.keys() if "dueño" not in k.lower() and "particular" not in k.lower()])
        top_excl_competencia = max(
            [item for item in adv_stats.items() if "remax" not in item[0].lower() and "dueño" not in item[0].lower()],
            key=lambda x: x[1]["excl_ap"],
            default=("N/A", {"excl_ap": 0, "total_ap": 1})
        )
        total_particulares = adv_stats.get("Dueño Directo / Particular", {}).get("total_ap", 0)
        excl_particulares = adv_stats.get("Dueño Directo / Particular", {}).get("excl_ap", 0)

        col_in1, col_in2, col_in3, col_in4 = st.columns(4)
        col_in1.metric("🏢 Inmobiliarias en Argenprop", total_inm)
        col_in2.metric("🏆 Mayor Exclusividad Competencia", top_excl_competencia[0][:22], f"{top_excl_competencia[1]['excl_ap']} exclusivas ({top_excl_competencia[1]['excl_ap']/max(1,top_excl_competencia[1]['total_ap'])*100:.0f}%)")
        col_in3.metric("👤 Dueños / Particulares AP", f"{total_particulares} props", f"{excl_particulares} exclusivas", delta_color="normal")
        col_in4.metric("🏠 Inmobiliarias en Zonaprop", len(zp_adv))

        st.write("---")

        st.markdown("#### ⚖️ Comparativa de Líderes: Argenprop vs Zonaprop")
        col_t1, col_t2 = st.columns(2)

        with col_t1:
            st.markdown("**Top 10 Anunciantes en Argenprop:**")
            top_ap_list = sorted(adv_stats.items(), key=lambda x: x[1]["total_ap"], reverse=True)[:10]
            df_top_ap = pd.DataFrame([
                {
                    "Anunciante / Inmobiliaria": k,
                    "Total AP": v["total_ap"],
                    "⭐ Exclusivas": v["excl_ap"],
                    "🔄 En Ambos": v["comp"],
                    "% Exclusiva": f"{v['excl_ap']/v['total_ap']*100:.1f}%"
                }
                for k, v in top_ap_list
            ])
            st.dataframe(df_top_ap, use_container_width=True, hide_index=True)

        with col_t2:
            st.markdown("**Top 10 Anunciantes en Zonaprop:**")
            top_zp_list = list(zp_adv.items())[:10]
            df_top_zp = pd.DataFrame([
                {
                    "Inmobiliaria Zonaprop": k,
                    "Total Props ZP": v,
                }
                for k, v in top_zp_list
            ])
            st.dataframe(df_top_zp, use_container_width=True, hide_index=True)

        st.write("---")

        st.markdown("#### 🔍 Tabla Completa de Anunciantes y Estrategia Comercial")
        filtro_cat = st.radio(
            "Filtrar por perfil comercial:",
            [
                "Todos los anunciantes",
                "⭐ Exclusivas de Argenprop (>70% fidelidad)",
                "🔄 Multicanal (Publican en Ambos Portales)",
                "👤 Dueños Directos y Particulares"
            ],
            horizontal=True
        )

        rows_all = []
        for name, s in adv_stats.items():
            tot = s["total_ap"]
            excl = s["excl_ap"]
            comp = s["comp"]
            pct = round((excl / tot) * 100, 1) if tot > 0 else 0

            is_part = "dueño" in name.lower() or "particular" in name.lower()

            if is_part:
                estrategia = "👤 Dueño Directo / Particular (Oportunidad de Captación)"
            elif pct >= 80:
                estrategia = "⭐ Fuerte en Argenprop (Casi sin Zonaprop)"
            elif pct >= 50:
                estrategia = "🟡 Prioriza Argenprop"
            else:
                estrategia = "🔄 Multicanal Activo (Publica en Ambos Portales)"

            if filtro_cat == "⭐ Exclusivas de Argenprop (>70% fidelidad)" and (pct < 70 or is_part):
                continue
            elif filtro_cat == "🔄 Multicanal (Publican en Ambos Portales)" and (comp < 10 or pct >= 70 or is_part):
                continue
            elif filtro_cat == "👤 Dueños Directos y Particulares" and not is_part:
                continue

            rows_all.append({
                "Anunciante / Inmobiliaria": name,
                "Total Argenprop": tot,
                "⭐ Exclusivas AP": excl,
                "🔄 En Ambos Portales": comp,
                "% Exclusiva": pct,
                "Estrategia Comercial": estrategia,
            })

        df_full = pd.DataFrame(rows_all)
        if not df_full.empty:
            df_full = df_full.sort_values(by="Total Argenprop", ascending=False).reset_index(drop=True)
            st.dataframe(
                df_full,
                column_config={
                    "Anunciante / Inmobiliaria": st.column_config.TextColumn("Anunciante / Inmobiliaria", width="large"),
                    "Total Argenprop": st.column_config.NumberColumn("Total Argenprop", format="%d"),
                    "⭐ Exclusivas AP": st.column_config.NumberColumn("⭐ Exclusivas AP", format="%d"),
                    "🔄 En Ambos Portales": st.column_config.NumberColumn("🔄 En Ambos Portales", format="%d"),
                    "% Exclusiva": st.column_config.ProgressColumn("% Exclusividad", format="%.1f%%", min_value=0, max_value=100),
                    "Estrategia Comercial": st.column_config.TextColumn("Estrategia Comercial", width="medium"),
                },
                use_container_width=True,
                height=450
            )

    st.stop()

filters = {
    "tipo_operacion": None if sel_op == "Todas" else sel_op,
    "tipo_propiedad": None if sel_type == "Todos" else sel_type,
    "barrio": None if sel_barrio == "Todos" else sel_barrio,
    "moneda": None if sel_moneda == "Todas" else sel_moneda,
    "min_price": min_p if min_p > 0 else None,
    "max_price": max_p if max_p > 0 else None,
    "min_dormitorios": min_dorms if min_dorms > 0 else None,
    "destaque": sel_destaque,
    "sort": sort_opt,
}

props, total_props = query_props(filters, limit=60)

st.title("🏢 Argenprop Salta — Catálogo de Propiedades")
st.caption("Propiedades en venta y alquiler extraídas en tiempo real desde Argenprop")

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Propiedades encontradas", total_props)
super_count = sum(1 for p in props if p.es_super_destacado or p.nivel_destacado == "super_destacado" or (p.visualizaciones and p.visualizaciones >= 2000))
col_m2.metric("Súper Destacadas en página", super_count)
views_avg = int(sum(p.visualizaciones or 0 for p in props) / max(1, len(props)))
col_m3.metric("Promedio visualizaciones", f"{views_avg:,}")

st.write("---")

if not props:
    st.info("No se encontraron propiedades con los filtros seleccionados.")
else:
    cols = st.columns(3)
    for idx, prop in enumerate(props):
        c = cols[idx % 3]
        with c:
            with st.container(border=True):
                # Imagen principal
                img = prop.imagen_principal or "https://via.placeholder.com/350x200?text=Sin+Foto"
                st.image(img, use_container_width=True)

                # Badges de Operación, Tipo, Destacado y Vistas
                badges_list = []
                badges_list.append(f'<span class="badge badge-op">{prop.tipo_operacion or "Venta"}</span>')
                badges_list.append(f'<span class="badge badge-type">{prop.tipo_propiedad or "Inmueble"}</span>')
                badges_list.append(get_destaque_badge(prop))
                if prop.visualizaciones:
                    badges_list.append(f'<span class="badge badge-views">👁️ {prop.visualizaciones:,}</span>')

                st.markdown("".join(badges_list), unsafe_allow_html=True)

                # Precio y Expensas
                price_txt = fmt_price(prop.precio, prop.moneda)
                exp_txt = f'<span class="expensas-text">+ ${prop.expensas:,.0f} exp.</span>' if prop.expensas else ""
                st.markdown(f'<div class="price-text">{price_txt} {exp_txt}</div>', unsafe_allow_html=True)

                # Título, Ubicación y Antigüedad
                titulo_display = prop.titulo or prop.direccion or "Sin título disponible"
                st.markdown(f"**{titulo_display[:50]}**")
                loc_str = prop.direccion or prop.barrio or prop.ubicacion or prop.localidad
                if prop.barrio and prop.barrio not in loc_str:
                    loc_str = f"{loc_str}, {prop.barrio}"
                meta_row = f"📍 {loc_str}"
                if prop.publicado_hace:
                    meta_row += f" · ⏱️ {prop.publicado_hace}"
                st.caption(meta_row)

                # Características (m2, dorms, baños)
                feats = []
                if prop.superficie_total:
                    feats.append(f"{prop.superficie_total:.0f} m²")
                if prop.dormitorios:
                    feats.append(f"{prop.dormitorios} dorm.")
                if prop.banos:
                    feats.append(f"{prop.banos} baños")
                if prop.cocheras:
                    feats.append(f"{prop.cocheras} coch.")
                st.markdown(f'<div class="features-text">📐 {" • ".join(feats) if feats else "Ver detalles"}</div>', unsafe_allow_html=True)

                # Botones de Acción
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("🔍 Ver detalle", key=f"btn_det_{prop.id}", use_container_width=True):
                        st.session_state.selected_id = prop.id
                        st.rerun()
                with btn_col2:
                    st.link_button("Argenprop ↗", prop.url, use_container_width=True)
