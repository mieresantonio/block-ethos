// Cliente del Tutor de Block Ethos (POST /api/tutor).
// El endpoint es público, igual que el contenido de las lecciones:
// no necesita sesión ni token. Con sesión, el token es opcional y
// el tutor usa el progreso del estudiante para guiar el siguiente
// paso; sin token responde igual que siempre.

const API = import.meta.env.VITE_BACKEND_URL;

export const askTutor = async (question, token = null) => {
    const headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const resp = await fetch(`${API}/api/tutor`, {
        method: "POST",
        headers,
        body: JSON.stringify({ question })
    });
    const data = await resp.json();
    if (!resp.ok) {
        throw new Error(data.error || "El tutor no pudo responder ahora");
    }
    return data;
};
