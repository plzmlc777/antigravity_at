// Version is injected by Vite at build time from package.json & git
export const APP_VERSION = "v0.8.9.9";
export const COMMIT_HASH = typeof __COMMIT_HASH__ !== 'undefined' ? __COMMIT_HASH__ : "dev";
export const BUILD_DATE = new Date().toISOString().split('T')[0];

const MOUNTAINS = [
    "Namsan (262m)",        // v0.0
    "Achasan (295m)",       // v0.1
    "Inwangsan (338m)",     // v0.2
    "Buramsan (508m)",      // v0.3
    "Cheonggyesan (582m)",  // v0.4
    "Gwanaksan (632m)",     // v0.5
    "Suraksan (638m)",      // v0.6
    "Dobongsan (740m)",     // v0.7
    "Bukhansan (836m)",     // v0.8 (Current)
    "Unaksan (935m)",       // v0.9
    "Chiaksan (1,288m)",    // v1.0
    "Odaesan (1,563m)",     // v1.1
    "Deogyusan (1,614m)",   // v1.2
    "Seoraksan (1,708m)",   // v1.3
    "Jirisan (1,915m)",     // v1.4
    "Hallasan (1,947m)",    // v1.5
    "Baekdusan (2,744m)",   // v1.6
    "Fuji (3,776m)"         // v1.7
];

export const getCodeName = () => {
    try {
        // Parse "v0.8.6" -> Major 0, Minor 8
        const cleanVer = APP_VERSION.replace('v', '');
        const parts = cleanVer.split('.');
        const major = parseInt(parts[0]);
        const minor = parseInt(parts[1]);

        // Logic: 0.x -> Index x, 1.x -> Index 10 + x
        let index = minor;
        if (major >= 1) {
            index = (major * 10) + minor;
        }

        if (index >= 0 && index < MOUNTAINS.length) {
            return MOUNTAINS[index];
        }
        return "Unknown Peak";
    } catch (e) {
        return "Base Camp";
    }
};

export const CODE_NAME = getCodeName();
