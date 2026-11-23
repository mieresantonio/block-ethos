// Cliente del perfil público verificable (/u/<handle>).
// La lectura pública no requiere sesión; la configuración (handle +
// opt-in) sí, y viaja con el token del store global, igual que el
// resto de la app construye sus cabeceras de autorización.

const API = import.meta.env.VITE_BACKEND_URL;

const authHeaders = (token) => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`
});

// Perfil público de un handle: 404 si no existe, si no es público o
// si no es de un estudiante (los tres casos responden igual).
export const getPublicProfile = async (handle) => {
    const resp = await fetch(
        `${API}/api/profile/${encodeURIComponent(handle)}`
    );
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error("No se pudo cargar el perfil público");
    return resp.json();
};

// Configuración del propio perfil (handle + visibilidad).
export const getMyProfile = async (token) => {
    const resp = await fetch(`${API}/api/profile/me`, {
        headers: authHeaders(token)
    });
    if (!resp.ok) throw new Error("No se pudo cargar tu perfil público");
    return resp.json();
};

// Cambia el handle y/o la visibilidad. El backend valida el handle
// (3-30 caracteres, sin reservados) y exige un handle antes de
// publicar. Un handle en uso responde 409 con su mensaje.
export const updateMyProfile = async (token, data) => {
    const resp = await fetch(`${API}/api/profile/me`, {
        method: "PUT",
        headers: authHeaders(token),
        body: JSON.stringify(data)
    });
    const body = await resp.json();
    if (!resp.ok) {
        throw new Error(body.error || "No se pudo guardar tu perfil público");
    }
    return body;
};
