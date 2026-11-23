import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import useGlobalReducer from "../hooks/useGlobalReducer";
import { ArrowRight, FileText, Flame, Award } from "lucide-react";
import { getGamification, getMyCertificates } from "../services/gamificationService";
import { getMyProfile, updateMyProfile } from "../services/profileService";

export const Dashboard = () => {
    const { store, dispatch } = useGlobalReducer();
    const navigate = useNavigate();
    const [progress, setProgress] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [usuario, setUsuario] = useState(null);
    const [gami, setGami] = useState(null);
    const [certs, setCerts] = useState([]);
    const [perfil, setPerfil] = useState(null);
    const [handleInput, setHandleInput] = useState("");
    const [perfilMsg, setPerfilMsg] = useState("");
    const [guardandoPerfil, setGuardandoPerfil] = useState(false);
    const [enlaceCopiado, setEnlaceCopiado] = useState(false);

    useEffect(() => {
        let activo = true;
        // Si no hay sesión iniciada, no tiene caso mostrar el panel: mandamos a login.
        if (!store.token) {
            navigate("/login");
            return () => { activo = false; };
        }

        const userGuardado = localStorage.getItem("user");
        if (userGuardado) {
            setUsuario(JSON.parse(userGuardado));
        }

        const cargarDatos = async () => {
            try {
                // 1. Trae los datos del usuario logueado.
                const dashboardResp = await fetch(
                    `${import.meta.env.VITE_BACKEND_URL}/api/dashboard`,
                    { headers: { Authorization: `Bearer ${store.token}` } }
                );
                if (!dashboardResp.ok) throw new Error("No se pudo cargar tu perfil");
                const dashboardData = await dashboardResp.json();
                if (!activo) return;
                dispatch({ type: "set_user", payload: dashboardData.user });

                // 2. Trae el progreso de lecciones de ese usuario (incluye
                //    lesson_title y path_id para poder armar el link directo).
                const progressResp = await fetch(
                    `${import.meta.env.VITE_BACKEND_URL}/api/progress/${dashboardData.user.id}`,
                    { headers: { Authorization: `Bearer ${store.token}` } }
                );
                if (!progressResp.ok) throw new Error("No se pudo cargar tu progreso");
                const progressData = await progressResp.json();
                if (!activo) return;
                setProgress(progressData);

                // Gamificación y certificados: si fallan, el panel
                // simplemente no muestra esas secciones.
                getGamification(store.token).then((g) => { if (activo) setGami(g); }).catch(() => {});
                getMyCertificates(store.token).then((c) => { if (activo) setCerts(c); }).catch(() => {});
                getMyProfile(store.token).then((p) => {
                    if (activo) { setPerfil(p); setHandleInput(p.handle || ""); }
                }).catch(() => {});
            } catch (err) {
                if (activo) setError(err.message);
            } finally {
                if (activo) setLoading(false);
            }
        };

        cargarDatos();
        return () => { activo = false; };
    }, [store.token]);

    if (loading) {
        return (
            <div className="container py-5 text-center">
                <div className="spinner-border text-primary" role="status">
                    <span className="visually-hidden">Cargando...</span>
                </div>
                <p className="text-muted small mt-3 mb-0">Cargando tu progreso...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="container py-5">
                <div className="alert alert-danger" role="alert">{error}</div>
                <button type="button" className="btn btn-primary rounded-pill px-4" onClick={() => window.location.reload()}>
                    Reintentar
                </button>
            </div>
        );
    }

    const completadas = progress.filter((p) => p.is_completed).length;
    const total = progress.length;
    const porcentaje = total > 0 ? Math.round((completadas / total) * 100) : 0;

    // Solo contamos como "aprobado" un quiz con nota >= 70%, igual que el
    // criterio real que ya usa QuizPage.jsx para marcar aprobación.
    const quizzesAprobados = progress.filter((p) => p.quiz_score !== null && p.quiz_score >= 70).length;

    // Primera lección sin completar: la que usamos para "Continuar aprendiendo".
    const siguienteLeccion = progress.find((p) => !p.is_completed);

    // Perfil público: guardar el handle, publicar/ocultar y copiar el
    // enlace. Los errores del backend (handle en uso, formato) se
    // muestran tal cual debajo del formulario.
    const guardarHandle = async () => {
        setPerfilMsg("");
        setGuardandoPerfil(true);
        try {
            const p = await updateMyProfile(store.token, { handle: handleInput });
            setPerfil(p);
            setPerfilMsg("Handle guardado.");
        } catch (e) {
            setPerfilMsg(e.message);
        } finally {
            setGuardandoPerfil(false);
        }
    };

    const cambiarVisibilidad = async () => {
        if (!perfil?.handle) {
            setPerfilMsg("Elige primero un handle para tu perfil público.");
            return;
        }
        setPerfilMsg("");
        setGuardandoPerfil(true);
        try {
            const p = await updateMyProfile(store.token, { is_public: !perfil.is_public });
            setPerfil(p);
            setPerfilMsg(p.is_public ? "Tu perfil público está activo." : "Tu perfil público está oculto.");
        } catch (e) {
            setPerfilMsg(e.message);
        } finally {
            setGuardandoPerfil(false);
        }
    };

    const copiarEnlacePerfil = async () => {
        const url = `${window.location.origin}/u/${perfil.handle}`;
        try {
            await navigator.clipboard.writeText(url);
        } catch {
            const area = document.createElement("textarea");
            area.value = url;
            document.body.appendChild(area);
            area.select();
            document.execCommand("copy");
            document.body.removeChild(area);
        }
        setEnlaceCopiado(true);
        setTimeout(() => setEnlaceCopiado(false), 2000);
    };

    if (!usuario || usuario.role !== "student") {
        return (
            <div className="container py-5 text-center">
                <h3 className="fw-bold">No disponible</h3>
                <p className="text-secondary">
                    Sección de estudiantes.
                </p>
            </div>
        );
    }

    return (
        <div className="container py-4">
            {/* Sin data-aos en la cabecera: está sobre el pliegue y debe
                verse a plena opacidad desde el primer instante; con AOS
                se veía tenue un momento al cargar (igual que el hero). */}
            <span className="badge bg-primary-subtle text-primary-emphasis mb-2">
                Panel del Estudiante
            </span>
            <h2 className="fw-bold mb-1">
                Bienvenido{store.user?.username ? `, ${store.user.username}` : ""}
            </h2>
            <p className="text-muted mb-4">
                Sigue avanzando en tu ruta de aprendizaje blockchain.
            </p>

            {gami && (
                <div className="card border-0 shadow-sm mb-4" data-aos="fade-up">
                    <div className="card-body p-4">
                        <div className="row align-items-center g-4">
                            <div className="col-12 col-md-6">
                                <span className="badge bg-warning-subtle text-warning-emphasis mb-2">
                                    Nivel · {gami.level_name}
                                </span>
                                <h4 className="fw-bold mb-2">
                                    {gami.xp} <span className="gradient-heading">XP</span>
                                </h4>
                                {gami.next_level_name ? (
                                    <>
                                        <div className="progress mb-2" role="progressbar" aria-label="Progreso hacia el siguiente nivel"
                                            aria-valuenow={Math.round(gami.progress_to_next * 100)} aria-valuemin={0} aria-valuemax={100} style={{ height: "10px" }}>
                                            <div className="progress-bar" style={{ width: `${Math.round(gami.progress_to_next * 100)}%` }}></div>
                                        </div>
                                        <p className="text-secondary small mb-0">
                                            Te faltan {gami.xp_to_next} XP para ser {gami.next_level_name}.
                                            Ganas 100 XP por lección y la nota de cada quiz suma.
                                        </p>
                                    </>
                                ) : (
                                    <p className="text-secondary small mb-0">
                                        Nivel máximo alcanzado. Eres de los primeros Arquitectos Web3 de Block Ethos.
                                    </p>
                                )}
                            </div>
                            <div className="col-6 col-md-3 text-center">
                                <Flame size={30} style={{ color: "#fb923c" }} />
                                <div className="fs-3 fw-bold">{gami.streak_current} días</div>
                                <div className="text-secondary small">
                                    racha actual · mejor: {gami.streak_best}
                                </div>
                            </div>
                            <div className="col-6 col-md-3 text-center">
                                <div className="fs-3 fw-bold text-primary">{gami.active_days}</div>
                                <div className="text-secondary small">días activos aprendiendo</div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {certs.length > 0 && (
                <div className="card border-0 shadow-sm mb-4" data-aos="fade-up">
                    <div className="card-body p-4">
                        <h5 className="fw-bold mb-3 d-flex align-items-center gap-2">
                            <Award size={20} style={{ color: "var(--bk-gold)" }} /> Mis certificados
                        </h5>
                        {certs.map((cert) => (
                            <div key={cert.id} className="d-flex justify-content-between align-items-center border-bottom py-2 flex-wrap gap-2">
                                <span>
                                    <b>{cert.path_title}</b>{" "}
                                    <small className="text-secondary mono">{cert.code}</small>
                                </span>
                                <Link to={`/certificado/${cert.path_id}`} className="btn btn-outline-primary btn-sm rounded-pill px-3">
                                    Ver certificado
                                </Link>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {perfil && (
                <div className="card border-0 shadow-sm mb-4">
                    <div className="card-body p-4">
                        <h5 className="fw-bold mb-2">Tu perfil público</h5>
                        <p className="text-secondary small mb-3">
                            Una página pública con tu progreso verificado para
                            enlazarla desde tu CV y LinkedIn. Solo se ve lo
                            que elijas publicar: nada se hace público hasta
                            que lo activas aquí.
                        </p>
                        <div className="d-flex gap-2 flex-wrap align-items-center mb-2">
                            <div className="input-group" style={{ maxWidth: "320px" }}>
                                <span className="input-group-text">/u/</span>
                                <input
                                    type="text"
                                    className="form-control"
                                    placeholder="tu-handle"
                                    aria-label="Handle de tu perfil público"
                                    value={handleInput}
                                    onChange={(e) => setHandleInput(e.target.value)}
                                    maxLength={30}
                                    disabled={guardandoPerfil}
                                />
                            </div>
                            <button
                                type="button"
                                className="btn btn-outline-primary rounded-pill px-3"
                                onClick={guardarHandle}
                                disabled={guardandoPerfil || !handleInput.trim()}
                            >
                                Guardar handle
                            </button>
                            <button
                                type="button"
                                className={`btn rounded-pill px-3 ${perfil.is_public ? "btn-outline-secondary" : "btn-primary"}`}
                                onClick={cambiarVisibilidad}
                                disabled={guardandoPerfil}
                            >
                                {perfil.is_public ? "Ocultar perfil" : "Publicar perfil"}
                            </button>
                        </div>
                        {perfilMsg && (
                            <p className="small mb-2" role="status">{perfilMsg}</p>
                        )}
                        {perfil.is_public && perfil.handle && (
                            <p className="small mb-0">
                                Tu perfil:{" "}
                                <Link to={`/u/${perfil.handle}`}>
                                    {window.location.origin}/u/{perfil.handle}
                                </Link>{" "}
                                <button
                                    type="button"
                                    className="btn btn-link btn-sm p-0"
                                    onClick={copiarEnlacePerfil}
                                >
                                    {enlaceCopiado ? "¡Copiado!" : "Copiar enlace"}
                                </button>
                            </p>
                        )}
                        <p className="text-secondary small mb-0 mt-2">
                            El handle debe tener 3–30 caracteres (minúsculas,
                            dígitos y puntos, guiones o guiones bajos). Si lo
                            cambias después de publicar, los enlaces antiguos
                            dejarán de funcionar.
                        </p>
                    </div>
                </div>
            )}

            {total > 0 && (
                <div className="row g-3 mb-4">
                    <div className="col-6 col-md-3">
                        <div className="card border-0 shadow-sm h-100 p-3 text-center" data-aos="fade-up">
                            <div className="fs-3 fw-bold text-primary">{porcentaje}%</div>
                            <div className="text-muted small">Completado</div>
                        </div>
                    </div>
                    <div className="col-6 col-md-3">
                        <div className="card border-0 shadow-sm h-100 p-3 text-center" data-aos="fade-up" data-aos-delay="50">
                            <div className="fs-3 fw-bold text-primary">{completadas}</div>
                            <div className="text-muted small">Lecciones hechas</div>
                        </div>
                    </div>
                    <div className="col-6 col-md-3">
                        <div className="card border-0 shadow-sm h-100 p-3 text-center" data-aos="fade-up" data-aos-delay="100">
                            <div className="fs-3 fw-bold text-primary">{quizzesAprobados}</div>
                            <div className="text-muted small">Quizzes aprobados</div>
                        </div>
                    </div>
                    <div className="col-6 col-md-3">
                        <div className="card border-0 shadow-sm h-100 p-3 text-center" data-aos="fade-up" data-aos-delay="150">
                            <div className="fs-3 fw-bold text-primary">{total}</div>
                            <div className="text-muted small">Lecciones vistas</div>
                        </div>
                    </div>
                </div>
            )}

            {siguienteLeccion && (
                <div className="card border-0 shadow-sm mb-4 text-white" style={{ background: "var(--bk-grad)" }} data-aos="fade-up">
                    <div className="card-body p-4 d-flex justify-content-between align-items-center flex-wrap gap-3">
                        <div>
                            <span className="badge mb-2" style={{ background: "#fff", color: "#4c1d95" }}>Continuar aprendiendo</span>
                            <h5 className="fw-bold mb-0 text-white">{siguienteLeccion.lesson_title}</h5>
                        </div>
                        <Link
                            to={`/lesson/${siguienteLeccion.path_id}/${siguienteLeccion.lesson_id}`}
                            className="btn rounded-pill px-4 fw-semibold d-inline-flex align-items-center gap-2"
                            style={{ background: "#fff", color: "#4c1d95" }}
                        >
                            Continuar <ArrowRight size={16} />
                        </Link>
                    </div>
                </div>
            )}

            <div className="card border-0 shadow-sm" data-aos="fade-up">
                <div className="card-body p-4">
                    <h5 className="fw-bold mb-3">Lecciones</h5>
                    {total === 0 && (
                        <p className="text-muted small mb-0">
                            Todavía no has empezado ninguna lección. Entra a "Explorar Rutas" para comenzar.
                        </p>
                    )}
                    {progress.map((item, i) => (
                        <Link
                            key={i}
                            to={`/lesson/${item.path_id}/${item.lesson_id}`}
                            className="d-flex justify-content-between align-items-center border-bottom py-3 text-decoration-none lesson-row-link"
                        >
                            <span className="d-inline-flex align-items-center text-break">
                                <FileText size={16} className="text-primary me-2 flex-shrink-0" />
                                {item.lesson_title || `Lección #${item.lesson_id}`}
                            </span>
                            <span className={`badge rounded-pill ${item.is_completed ? "bg-success" : "bg-secondary"}`}>
                                {item.is_completed ? "Completada" : "En progreso"}
                            </span>
                        </Link>
                    ))}
                </div>
            </div>
        </div>
    );
}; 