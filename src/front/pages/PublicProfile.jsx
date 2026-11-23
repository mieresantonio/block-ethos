import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getPublicProfile } from "../services/profileService";
import { ShieldCheck, Award, UserX } from "lucide-react";

// Perfil público verificable (/u/<handle>): página pública por
// estudiante, pensada para enlazarla desde el CV y LinkedIn como
// credencial. Solo muestra lo que el estudiante eligió hacer
// público (opt-in): nombre, nivel, XP y rutas con su avance y sus
// certificados. Cada certificado enlaza a su página de verificación
// (/verificar/<código>), donde cualquiera puede comprobarlo de
// forma independiente: esa es la verificación, no una afirmación
// de la propia página.

const MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
];

const formatearMiembroDesde = (valor) => {
    if (!valor || !/^\d{4}-\d{2}$/.test(valor)) return null;
    const [anio, mes] = valor.split("-").map(Number);
    if (mes < 1 || mes > 12) return null;
    return `${MESES[mes - 1]} de ${anio}`;
};

export const PublicProfile = () => {
    const { handle } = useParams();
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);

    useEffect(() => {
        let activo = true;
        setLoading(true);
        setNotFound(false);
        getPublicProfile(handle)
            .then((res) => {
                if (!activo) return;
                if (res === null) {
                    setNotFound(true);
                } else {
                    setProfile(res);
                }
            })
            .catch(() => { if (activo) setNotFound(true); })
            .finally(() => { if (activo) setLoading(false); });
        return () => { activo = false; };
    }, [handle]);

    useEffect(() => {
        if (profile) {
            document.title = `${profile.display_name} (@${profile.handle}) · Block Ethos`;
        }
        return () => { document.title = "Block Ethos"; };
    }, [profile]);

    if (loading) {
        return (
            <div className="container py-5 text-center">
                <div className="spinner-border text-primary" role="status">
                    <span className="visually-hidden">Cargando el perfil…</span>
                </div>
                <p className="text-secondary small mt-3">Cargando el perfil…</p>
            </div>
        );
    }

    if (notFound || !profile) {
        return (
            <div className="container py-5" style={{ maxWidth: "640px" }}>
                <div className="card bk-hover p-4 p-md-5 text-center">
                    <span className="icon-chip mx-auto mb-3">
                        <UserX size={24} />
                    </span>
                    <h3 className="fw-bold mb-2">Perfil no encontrado</h3>
                    <p className="text-secondary mb-4">
                        No hay ningún perfil público de Block Ethos con el
                        handle <b className="mono">@{handle}</b>. Puede que
                        no exista o que su dueño lo tenga privado.
                    </p>
                    <Link to="/" className="btn btn-primary rounded-pill px-4">
                        Conocer Block Ethos
                    </Link>
                </div>
            </div>
        );
    }

    const miembroDesde = formatearMiembroDesde(profile.member_since);

    return (
        <div className="container py-5" style={{ maxWidth: "760px" }}>
            <div className="card border-0 shadow-sm mb-4">
                <div className="card-body p-4 p-md-5 text-center">
                    <div
                        className="rounded-circle d-inline-flex align-items-center justify-content-center fw-bold text-white mb-3"
                        style={{ width: "72px", height: "72px", fontSize: "2rem", background: "var(--bk-grad)" }}
                        aria-hidden="true"
                    >
                        {(profile.display_name || profile.handle || "?").charAt(0).toUpperCase()}
                    </div>
                    <h2 className="fw-bold mb-1">{profile.display_name}</h2>
                    <p className="text-secondary mb-3">@{profile.handle}</p>
                    <div className="d-flex flex-wrap justify-content-center gap-2 mb-3">
                        <span className="badge bg-warning-subtle text-warning-emphasis">
                            Nivel · {profile.level_name}
                        </span>
                        <span className="badge bg-primary-subtle text-primary-emphasis">
                            {profile.xp} XP
                        </span>
                        <span className="badge bg-success-subtle text-success-emphasis d-inline-flex align-items-center gap-1">
                            <ShieldCheck size={13} /> Verificado por Block Ethos
                        </span>
                    </div>
                    {miembroDesde && (
                        <p className="text-secondary small mb-0">
                            Estudiante desde {miembroDesde}
                        </p>
                    )}
                </div>
            </div>

            <div className="card border-0 shadow-sm mb-4">
                <div className="card-body p-4">
                    <h5 className="fw-bold mb-3 d-flex align-items-center gap-2">
                        <Award size={20} style={{ color: "var(--bk-gold)" }} /> Rutas de aprendizaje
                    </h5>
                    {profile.paths.length === 0 && (
                        <p className="text-muted small mb-0">
                            Todavía no hay rutas empezadas en este perfil.
                        </p>
                    )}
                    {profile.paths.map((ruta) => (
                        <div key={ruta.path_id} className="border-bottom py-3">
                            <div className="d-flex justify-content-between align-items-baseline flex-wrap gap-2">
                                <b>{ruta.title}</b>
                                <small className="text-secondary">
                                    {ruta.lessons_completed} de {ruta.lessons_total} lecciones · {ruta.percent}%
                                </small>
                            </div>
                            <div className="progress mt-2" role="progressbar"
                                aria-label={`Avance en ${ruta.title}`}
                                aria-valuenow={ruta.percent} aria-valuemin={0} aria-valuemax={100}
                                style={{ height: "8px" }}>
                                <div className="progress-bar" style={{ width: `${ruta.percent}%` }}></div>
                            </div>
                            {ruta.certificate ? (
                                <p className="small mt-2 mb-0">
                                    <ShieldCheck size={14} className="text-success me-1" />
                                    Certificado{" "}
                                    <Link to={`/verificar/${ruta.certificate.code}`} className="mono">
                                        {ruta.certificate.code}
                                    </Link>
                                    {" "}·{" "}
                                    {ruta.certificate.issued_at
                                        ? new Date(ruta.certificate.issued_at).toLocaleDateString("es-ES", {
                                              day: "numeric", month: "long", year: "numeric"
                                          })
                                        : "sin fecha"}
                                </p>
                            ) : (
                                <p className="text-secondary small mt-2 mb-0">
                                    En progreso: el certificado aparece aquí al completar la ruta.
                                </p>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            <p className="text-secondary small text-center mb-0">
                Este perfil lo publica su dueño desde Block Ethos. Cada
                certificado se puede comprobar por su cuenta en su página
                de verificación.
            </p>
        </div>
    );
};
