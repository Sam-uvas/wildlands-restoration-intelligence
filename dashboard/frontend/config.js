/*
 * WILDLANDS — Central API Configuration
 */

const WILDLANDS_CONFIG = {
    API_BASE_URL:
        window.WILDLANDS_API_BASE_URL ||
        "https://wildlands-api.onrender.com"
};

const API_BASE_URL = WILDLANDS_CONFIG.API_BASE_URL;

function apiUrl(path) {
    if (!path.startsWith("/")){
        path = "/" + path;
    }

    return API_BASE_URL.replace(/\/$/, "") + path;
}
