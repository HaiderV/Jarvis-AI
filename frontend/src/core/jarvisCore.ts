/**
 * jarvisCore.ts — v4 (Stark Holographic Core)
 * ---------------------------------------------------------------------------
 * A 3D holographic sphere modeled after Tony Stark's JARVIS AI core:
 *  - Concentric 3D gimbal rings with tech tick graduations and segmented tracks.
 *  - 3D spherical tech cage with longitude meridians and latitude parallels.
 *  - High-intensity central plasma arc reactor / nucleus with radiant bloom.
 *  - Distinct, expressive state-driven animations:
 *      * IDLE: Majestic slow gyroscopic tumble, calm breathing, ambient sparks.
 *      * LISTENING: Rings face viewer like an acoustic dish, micro-frequency
 *                   soundwave ripples vibrating along the tracks, focused eye.
 *      * THINKING: High-speed counter-rotating gyroscopes, rapid computation
 *                  strobing in the core, streaming data dashes, scan beam.
 *      * SPEAKING: Resonant vocal expansion, expanding acoustic shockwaves
 *                  synchronized with word delivery, warm radiant bloom.
 */

export type CoreState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface JarvisCoreHandle {
    setState(next: CoreState): void;
    /** brightens the core and triggers vocal acoustic shockwave */
    pulse(strength?: number): void;
    setPointer(x: number, y: number, inside: boolean): void;
    resize(width: number, height: number, dpr: number): void;
    destroy(): void;
}

const TAU = Math.PI * 2;
const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/* ------------------------------------------------------------------ palette */

const PALETTE: [number, number, number][] = [
    [255, 252, 240], // 0: Incandescent White-hot Core
    [255, 228, 140], // 1: Pale Radiant Gold
    [255, 185, 50],  // 2: Stark Pure Gold
    [255, 135, 20],  // 3: Warm Amber
    [225, 80, 10],   // 4: Vivid Flame Orange
    [150, 35, 5],    // 5: Deep Holographic Ember
];

const rgba = (tint: number, a: number) => {
    const c = PALETTE[clamp(tint, 0, PALETTE.length - 1)];
    return `rgba(${c[0]},${c[1]},${c[2]},${clamp(a, 0, 1)})`;
};

function makeSprite(tint: number, tight = 1): HTMLCanvasElement {
    const size = 128;
    const cv = document.createElement('canvas');
    cv.width = size;
    cv.height = size;
    const c = cv.getContext('2d')!;
    const [r, g, b] = PALETTE[tint];
    const grad = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    grad.addColorStop(0, `rgba(${r},${g},${b},1)`);
    grad.addColorStop(0.18 * tight, `rgba(${r},${g},${b},0.75)`);
    grad.addColorStop(0.44 * tight, `rgba(${r},${g},${b},0.28)`);
    grad.addColorStop(0.75 * tight, `rgba(${r},${g},${b},0.07)`);
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
    c.fillStyle = grad;
    c.fillRect(0, 0, size, size);
    return cv;
}

/* ------------------------------------------------------------------ helpers */

function computeBasis(nx: number, ny: number, nz: number): {
    ux: number; uy: number; uz: number;
    vx: number; vy: number; vz: number;
} {
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len;
    ny /= len;
    nz /= len;

    // Pick a vector not parallel to n
    let wx = 1, wy = 0, wz = 0;
    if (Math.abs(nx) > 0.88) {
        wx = 0; wy = 1; wz = 0;
    }

    // u = normalize(n x w)
    let ux = ny * wz - nz * wy;
    let uy = nz * wx - nx * wz;
    let uz = nx * wy - ny * wx;
    const ulen = Math.hypot(ux, uy, uz) || 1;
    ux /= ulen; uy /= ulen; uz /= ulen;

    // v = n x u
    const vx = ny * uz - nz * uy;
    const vy = nz * ux - nx * uz;
    const vz = nx * uy - ny * ux;

    return { ux, uy, uz, vx, vy, vz };
}

/* ------------------------------------------------------------------ types */

interface GimbalRing {
    id: string;
    rad: number;
    nx: number; ny: number; nz: number;
    ux: number; uy: number; uz: number;
    vx: number; vy: number; vz: number;
    spinSpeed: number; // rad/sec
    angle: number;
    style: 'dial' | 'double' | 'dashed' | 'notched' | 'brackets' | 'iris';
    ticksCount: number;
    tickLen: number;
    nodesCount: number;
    tint: number;
    width: number;
}

interface Soundwave {
    rad: number;
    maxRad: number;
    alpha: number;
    speed: number;
}

interface Ember {
    x: number;
    y: number;
    vx: number;
    vy: number;
    life: number;
    max: number;
    size: number;
    tint: number;
}

/* ----------------------------------------------------------------- engine */

export function createJarvisCore(canvas: HTMLCanvasElement): JarvisCoreHandle {
    const ctx = canvas.getContext('2d', { alpha: true })!;
    const sprites = PALETTE.map((_, i) => makeSprite(i, i === 0 ? 0.6 : 1));

    let w = 0;
    let h = 0;
    let dpr = 1;
    let R = 1;
    let cx = 0;
    let cy = 0;

    let raf = 0;
    let last = 0;
    let t = 0;
    let running = true;

    let state: CoreState = 'idle';

    // Interpolated state parameters
    const cur = {
        scale: 1,
        spin: 1,
        energy: 0.65,
        vibe: 0,
        faceCam: 0,
        pulseFreq: 0.7,
        scan: 0,
        bloom: 1,
    };
    const tgt = {
        scale: 1,
        spin: 1,
        energy: 0.65,
        vibe: 0,
        faceCam: 0,
        pulseFreq: 0.7,
        scan: 0,
        bloom: 1,
    };

    const ptr = { x: 0, y: 0, tx: 0, ty: 0, inside: false };

    let glow = 0;
    let soundwaves: Soundwave[] = [];
    let vocalTimer = 0;
    let embers: Ember[] = [];

    // Smooth continuous angle integrators (prevents jumps during state transitions)
    let camYawAngle = 0;
    let dustAngle = 0;
    let coreArcAngle = 0;
    let latAngle = 0;

    // Tech Gimbal Rings
    let gimbalRings: GimbalRing[] = [];

    // Volumetric 3D Data Particles
    let dustN = 280;
    let dustX = new Float32Array(dustN);
    let dustY = new Float32Array(dustN);
    let dustZ = new Float32Array(dustN);
    let dustSeed = new Float32Array(dustN);
    let dustTint = new Uint8Array(dustN);

    /* ---------------------------------------------------------- population */

    function buildRings() {
        // Ring configurations reflecting the Stark holographic sphere in reference image:
        const configs: Array<{
            id: string;
            rad: number;
            n: [number, number, number];
            spinSpeed: number;
            style: GimbalRing['style'];
            ticksCount: number;
            tickLen: number;
            nodesCount: number;
            tint: number;
            width: number;
        }> = [
            {
                id: 'dial-outer',
                rad: 1.05,
                n: [0, 0.08, 0.99],
                spinSpeed: 0.018,
                style: 'dial',
                ticksCount: 72,
                tickLen: 0.035,
                nodesCount: 4,
                tint: 2,
                width: 1.1,
            },
            {
                id: 'equator-double',
                rad: 0.94,
                n: [0, 1, 0],
                spinSpeed: 0.032,
                style: 'double',
                ticksCount: 24,
                tickLen: 0.024,
                nodesCount: 5,
                tint: 1,
                width: 1.2,
            },
            {
                id: 'gimbal-a',
                rad: 0.82,
                n: [0, Math.cos(0.65), Math.sin(0.65)],
                spinSpeed: -0.042, // Counter-rotating!
                style: 'dashed',
                ticksCount: 36,
                tickLen: 0.03,
                nodesCount: 4,
                tint: 2,
                width: 1.3,
            },
            {
                id: 'gimbal-b',
                rad: 0.70,
                n: [Math.sin(0.85), Math.cos(0.85), 0],
                spinSpeed: 0.048,
                style: 'notched',
                ticksCount: 32,
                tickLen: 0.026,
                nodesCount: 3,
                tint: 1,
                width: 1.2,
            },
            {
                id: 'gimbal-c',
                rad: 0.52,
                n: [0.42, 0.75, 0.5],
                spinSpeed: -0.058, // Counter-rotating inner!
                style: 'brackets',
                ticksCount: 16,
                tickLen: 0.032,
                nodesCount: 3,
                tint: 2,
                width: 1.4,
            },
            {
                id: 'iris-core',
                rad: 0.34,
                n: [0.15, 0.95, 0.25],
                spinSpeed: 0.075,
                style: 'iris',
                ticksCount: 12,
                tickLen: 0.025,
                nodesCount: 2,
                tint: 0,
                width: 1.5,
            },
        ];

        gimbalRings = configs.map((cfg) => {
            const b = computeBasis(cfg.n[0], cfg.n[1], cfg.n[2]);
            return {
                id: cfg.id,
                rad: cfg.rad,
                nx: cfg.n[0],
                ny: cfg.n[1],
                nz: cfg.n[2],
                ux: b.ux,
                uy: b.uy,
                uz: b.uz,
                vx: b.vx,
                vy: b.vy,
                vz: b.vz,
                spinSpeed: cfg.spinSpeed,
                angle: Math.random() * TAU,
                style: cfg.style,
                ticksCount: cfg.ticksCount,
                tickLen: cfg.tickLen,
                nodesCount: cfg.nodesCount,
                tint: cfg.tint,
                width: cfg.width,
            };
        });

        // Generate 3D volumetric particles
        dustN = Math.round(clamp((w * h) / 1800, 220, 360));
        dustX = new Float32Array(dustN);
        dustY = new Float32Array(dustN);
        dustZ = new Float32Array(dustN);
        dustSeed = new Float32Array(dustN);
        dustTint = new Uint8Array(dustN);

        for (let i = 0; i < dustN; i++) {
            const phi = Math.acos(2 * Math.random() - 1);
            const theta = Math.random() * TAU;
            const r = Math.pow(Math.random(), 0.65) * 0.98;
            dustX[i] = Math.sin(phi) * Math.cos(theta) * r;
            dustY[i] = Math.cos(phi) * r;
            dustZ[i] = Math.sin(phi) * Math.sin(theta) * r;
            dustSeed[i] = Math.random() * 100;
            dustTint[i] = r < 0.35 ? 0 : r < 0.7 ? 1 : Math.random() < 0.6 ? 2 : 3;
        }

        soundwaves = [];
        embers = [];
    }

    function spawnSoundwave(strength = 0.5) {
        soundwaves.push({
            rad: 0.12,
            maxRad: 1.18,
            alpha: 0.75 + clamp(strength, 0, 0.25),
            speed: 1.35 + strength * 0.4,
        });
    }

    function emitEmbers(n: number) {
        for (let i = 0; i < n; i++) {
            const a = Math.random() * TAU;
            const r0 = R * (0.6 + Math.random() * 0.4);
            const sp = R * (0.15 + Math.random() * 0.35);
            embers.push({
                x: Math.cos(a) * r0,
                y: Math.sin(a) * r0,
                vx: Math.cos(a) * sp,
                vy: Math.sin(a) * sp,
                life: 1,
                max: 0.9 + Math.random() * 1.4,
                size: 0.8 + Math.random() * 1.5,
                tint: Math.random() < 0.4 ? 1 : 2,
            });
        }
    }

    /* ------------------------------------------------------------- 3D math */

    function project3D(
        x: number,
        y: number,
        z: number,
        scale: number,
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
    ) {
        // Yaw (around Y axis)
        const x1 = x * cosY + z * sinY;
        const z1 = -x * sinY + z * cosY;
        // Pitch (around X axis)
        const y1 = y * cosX - z1 * sinX;
        const z2 = y * sinX + z1 * cosX;

        const fov = 2.8;
        const persp = fov / (fov + z2 * 0.85);
        const px = cx + x1 * scale * R * persp;
        const py = cy + y1 * scale * R * persp;
        const depth = clamp((z2 + 1) / 2, 0, 1);
        return { px, py, z: z2, depth, persp };
    }

    /* ----------------------------------------------------------- rendering */

    function drawTechGimbalRing(
        ring: GimbalRing,
        scale: number,
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
    ) {
        const segs = 72;
        const spin = ring.angle;
        const baseRadius = ring.rad * scale;

        // In listening state, the acoustic wave vibrates the ring radius
        const vibeActive = cur.vibe;

        // In listening state, smoothly steer ring normal towards viewer
        const faceK = cur.faceCam * 0.55;
        let ux = ring.ux;
        let uy = ring.uy;
        let uz = ring.uz;
        let vx = ring.vx;
        let vy = ring.vy;
        let vz = ring.vz;

        if (faceK > 0.01) {
            // blend basis towards screen-aligned plane (X, Y)
            ux = lerp(ux, 1, faceK * 0.3);
            vy = lerp(vy, 1, faceK * 0.3);
            uz = lerp(uz, 0, faceK * 0.5);
            vz = lerp(vz, 0, faceK * 0.5);
        }

        // Draw the ring circumference
        ctx.beginPath();
        let firstDrawn = false;
        let avgZ = 0;

        for (let i = 0; i <= segs; i++) {
            const frac = i / segs;
            const theta = frac * TAU;
            const rotTheta = theta + spin;

            // Acoustic ripple waveform along the ring circumference in listening mode
            const wave = vibeActive > 0.02
                ? Math.sin(theta * 7 + t * 16) * 0.035 * vibeActive
                : 0;

            const rEff = baseRadius * (1 + wave);
            const cs = Math.cos(rotTheta);
            const sn = Math.sin(rotTheta);

            const rx = (ux * cs + vx * sn) * rEff;
            const ry = (uy * cs + vy * sn) * rEff;
            const rz = (uz * cs + vz * sn) * rEff;

            const pt = project3D(rx, ry, rz, 1, cosY, sinY, cosX, sinX);
            avgZ += pt.z;

            if (!firstDrawn) {
                ctx.moveTo(pt.px, pt.py);
                firstDrawn = true;
            } else {
                ctx.lineTo(pt.px, pt.py);
            }
        }

        avgZ /= segs + 1;
        const ringDepth = clamp((avgZ + 1) / 2, 0, 1);
        const limbGlow = Math.pow(1 - Math.abs(avgZ), 1.6);
        const alpha = clamp(
            (0.18 + 0.55 * ringDepth + 0.3 * limbGlow) *
            (0.6 + 0.45 * cur.energy) *
            (0.85 + 0.4 * glow),
            0,
            0.95,
        );

        ctx.strokeStyle = rgba(ring.tint, alpha);
        ctx.lineWidth = ring.width * (0.7 + ringDepth * 0.5);

        if (ring.style === 'dashed') {
            // Fast streaming dashes in thinking state
            const dashScale = cur.spin > 2 ? 1.5 : 1;
            ctx.setLineDash([14 * dashScale, 8, 4, 8]);
        } else if (ring.style === 'brackets') {
            ctx.setLineDash([28, 16]);
        } else if (ring.style === 'iris') {
            ctx.setLineDash([12, 6]);
        } else {
            ctx.setLineDash([]);
        }

        ctx.stroke();

        // If double track, stroke an inner concentric line
        if (ring.style === 'double') {
            ctx.beginPath();
            const innerRadius = baseRadius * 0.965;
            for (let i = 0; i <= segs; i++) {
                const frac = i / segs;
                const theta = frac * TAU + spin;
                const cs = Math.cos(theta);
                const sn = Math.sin(theta);
                const rx = (ux * cs + vx * sn) * innerRadius;
                const ry = (uy * cs + vy * sn) * innerRadius;
                const rz = (uz * cs + vz * sn) * innerRadius;
                const pt = project3D(rx, ry, rz, 1, cosY, sinY, cosX, sinX);
                if (i === 0) ctx.moveTo(pt.px, pt.py);
                else ctx.lineTo(pt.px, pt.py);
            }
            ctx.strokeStyle = rgba(ring.tint + 1, alpha * 0.7);
            ctx.lineWidth = ring.width * 0.75;
            ctx.setLineDash([8, 8]);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Draw radial tech ticks (calibration notches) around the gimbal ring
        if (ring.ticksCount > 0) {
            ctx.beginPath();
            const count = ring.ticksCount;
            const tLen = ring.tickLen * (cur.spin > 2 ? 1.25 : 1);

            for (let k = 0; k < count; k++) {
                const theta = (k / count) * TAU + spin;
                const cs = Math.cos(theta);
                const sn = Math.sin(theta);

                // Major tick every quarter or 6th
                const isMajor = k % 6 === 0;
                const thisLen = isMajor ? tLen * 1.6 : tLen;

                // Base point on ring
                const bx = (ux * cs + vx * sn) * baseRadius;
                const by = (uy * cs + vy * sn) * baseRadius;
                const bz = (uz * cs + vz * sn) * baseRadius;
                const p0 = project3D(bx, by, bz, 1, cosY, sinY, cosX, sinX);

                // Tip point radiating outward
                const tx = (ux * cs + vx * sn) * (baseRadius + thisLen);
                const ty = (uy * cs + vy * sn) * (baseRadius + thisLen);
                const tz = (uz * cs + vz * sn) * (baseRadius + thisLen);
                const p1 = project3D(tx, ty, tz, 1, cosY, sinY, cosX, sinX);

                ctx.moveTo(p0.px, p0.py);
                ctx.lineTo(p1.px, p1.py);
            }

            ctx.strokeStyle = rgba(ring.tint, alpha * 0.8);
            ctx.lineWidth = ring.width * 0.8;
            ctx.setLineDash([]);
            ctx.stroke();
        }

        // Draw glowing tech data nodes along the ring
        if (ring.nodesCount > 0) {
            const count = ring.nodesCount;
            for (let n = 0; n < count; n++) {
                const theta = (n / count) * TAU + spin * 1.4;
                const cs = Math.cos(theta);
                const sn = Math.sin(theta);
                const rx = (ux * cs + vx * sn) * baseRadius;
                const ry = (uy * cs + vy * sn) * baseRadius;
                const rz = (uz * cs + vz * sn) * baseRadius;
                const pt = project3D(rx, ry, rz, 1, cosY, sinY, cosX, sinX);

                if (pt.depth > 0.15) {
                    const nodeAlpha = clamp(alpha * (0.8 + 0.4 * Math.sin(t * 4 + n)), 0, 1);
                    ctx.fillStyle = rgba(0, nodeAlpha);
                    ctx.beginPath();
                    const sz = (ring.width + 1.2) * pt.persp;
                    ctx.arc(pt.px, pt.py, sz, 0, TAU);
                    ctx.fill();
                }
            }
        }
    }

    function drawSphericalCage(
        scale: number,
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
    ) {
        // Draw 3D longitude meridians (great circles outlining the holographic sphere)
        const longitudes = [0, Math.PI / 4, Math.PI / 2, (3 * Math.PI) / 4];
        const steps = 36;
        const cageRadius = 0.98 * scale;

        ctx.setLineDash([4, 8]);
        ctx.lineWidth = 0.85;

        for (let l = 0; l < longitudes.length; l++) {
            const lon = longitudes[l];
            const cosL = Math.cos(lon);
            const sinL = Math.sin(lon);

            ctx.beginPath();
            let first = true;
            let sumZ = 0;

            for (let s = 0; s <= steps; s++) {
                const lat = (s / steps) * TAU;
                const cosLat = Math.cos(lat);
                const sinLat = Math.sin(lat);

                // Point on sphere surface
                const x = cageRadius * cosLat * cosL;
                const y = cageRadius * sinLat;
                const z = cageRadius * cosLat * sinL;

                const pt = project3D(x, y, z, 1, cosY, sinY, cosX, sinX);
                sumZ += pt.z;

                if (first) {
                    ctx.moveTo(pt.px, pt.py);
                    first = false;
                } else {
                    ctx.lineTo(pt.px, pt.py);
                }
            }

            const avgZ = sumZ / (steps + 1);
            const alpha = clamp(
                (0.12 + 0.28 * ((avgZ + 1) / 2)) * (0.55 + 0.45 * cur.energy),
                0,
                0.6,
            );
            ctx.strokeStyle = rgba(3, alpha);
            ctx.stroke();
        }

        // Draw 2 Latitude parallels (upper and lower tech equator rings)
        const latitudes = [0.55, -0.55]; // ~32 deg N and S
        for (let la = 0; la < latitudes.length; la++) {
            const y0 = cageRadius * latitudes[la];
            const rLat = cageRadius * Math.sqrt(Math.max(0, 1 - latitudes[la] * latitudes[la]));

            ctx.beginPath();
            let first = true;
            for (let s = 0; s <= steps; s++) {
                const theta = (s / steps) * TAU + latAngle * (la === 0 ? 1 : -1);
                const x = rLat * Math.cos(theta);
                const z = rLat * Math.sin(theta);
                const pt = project3D(x, y0, z, 1, cosY, sinY, cosX, sinX);

                if (first) {
                    ctx.moveTo(pt.px, pt.py);
                    first = false;
                } else {
                    ctx.lineTo(pt.px, pt.py);
                }
            }
            ctx.strokeStyle = rgba(2, 0.22 * (0.6 + 0.4 * cur.energy));
            ctx.setLineDash([3, 7]);
            ctx.stroke();
        }
        ctx.setLineDash([]);
    }

    function drawCentralArcReactor(scale: number) {
        // High-intensity central plasma nucleus (Stark Arc Reactor core)
        const pulseHarmonic = Math.sin(t * TAU * cur.pulseFreq);
        const pulse = 0.8 + 0.2 * pulseHarmonic + 0.35 * glow;

        // In thinking state: fast jitter in the core reflecting neural calculation
        const jitter = cur.scan > 0.5 ? (Math.random() - 0.5) * 0.04 : 0;
        const coreScale = scale * (1 + jitter);

        // 1. Warm outer ambient corona
        const coronaSize = Math.max(0, R * 1.8 * coreScale * cur.bloom);
        ctx.globalAlpha = clamp((0.18 + 0.12 * cur.energy + 0.15 * glow) * pulse, 0, 1);
        ctx.drawImage(sprites[4], cx - coronaSize / 2, cy - coronaSize / 2, coronaSize, coronaSize);

        // 2. Mid golden bloom
        const midSize = Math.max(0, R * 0.85 * coreScale * cur.bloom);
        ctx.globalAlpha = clamp((0.35 + 0.25 * cur.energy + 0.25 * glow) * pulse, 0, 1);
        ctx.drawImage(sprites[2], cx - midSize / 2, cy - midSize / 2, midSize, midSize);

        // 3. Radiant inner reactor iris
        const innerSize = Math.max(0, R * 0.42 * coreScale * pulse);
        ctx.globalAlpha = clamp(0.75 + 0.25 * glow, 0, 1);
        ctx.drawImage(sprites[1], cx - innerSize / 2, cy - innerSize / 2, innerSize, innerSize);

        // 4. White-hot plasma nucleus (pure incandescent center)
        const hotSize = Math.max(0, R * 0.16 * coreScale * pulse);
        ctx.globalAlpha = clamp(0.92 + 0.08 * glow, 0, 1);
        ctx.drawImage(sprites[0], cx - hotSize / 2, cy - hotSize / 2, hotSize, hotSize);

        // 5. Anamorphic horizontal holographic lens flare beam
        const flareW = Math.max(0, R * 2.2 * coreScale * (0.85 + 0.25 * pulse + 0.3 * glow));
        const flareH = Math.max(0, R * 0.032 * coreScale);
        ctx.globalAlpha = clamp(0.28 + 0.2 * cur.energy + 0.25 * glow, 0, 1);
        ctx.drawImage(sprites[1], cx - flareW / 2, cy - flareH / 2, flareW, flareH);

        // 6. Fast spinning plasma micro-arcs in the nucleus
        const arcCount = 6;
        ctx.setLineDash([]);
        for (let i = 0; i < arcCount; i++) {
            const rot = coreArcAngle * (1 + i * 0.18) + (i / arcCount) * TAU;
            const rMin = R * 0.05 * coreScale;
            const rMax = R * (0.16 + (i % 3) * 0.04) * coreScale;
            ctx.beginPath();
            ctx.ellipse(cx, cy, rMax, rMin, rot, 0, Math.PI * 0.85);
            ctx.strokeStyle = rgba(i % 2 === 0 ? 0 : 1, clamp(0.55 * pulse, 0, 0.9));
            ctx.lineWidth = 1.2;
            ctx.stroke();
        }

        ctx.globalAlpha = 1;
    }

    function drawSoundwaves() {
        if (soundwaves.length === 0) return;
        ctx.setLineDash([]);

        for (let i = soundwaves.length - 1; i >= 0; i--) {
            const sw = soundwaves[i];
            const pxRad = R * sw.rad;
            const alpha = sw.alpha * (1 - sw.rad / sw.maxRad);

            if (alpha > 0.02) {
                // Expanding resonant acoustic circle
                ctx.beginPath();
                ctx.arc(cx, cy, pxRad, 0, TAU);
                ctx.strokeStyle = rgba(1, clamp(alpha * 0.7, 0, 0.85));
                ctx.lineWidth = 1.8 * (1 - sw.rad / sw.maxRad) + 0.8;
                ctx.stroke();

                // Faint outer echo ring
                ctx.beginPath();
                ctx.arc(cx, cy, pxRad * 0.92, 0, TAU);
                ctx.strokeStyle = rgba(2, clamp(alpha * 0.35, 0, 0.5));
                ctx.lineWidth = 1;
                ctx.stroke();
            }

            if (sw.rad >= sw.maxRad || alpha <= 0.01) {
                soundwaves.splice(i, 1);
            }
        }
    }

    function drawScanPlane(scale: number) {
        if (cur.scan < 0.05) return;
        // In thinking state: active sweeping holographic scan-plane
        const scanY = (Math.sin(t * 1.6) * 0.75) * R * scale;
        const widthHalf = Math.sqrt(Math.max(0, Math.pow(R * scale * 0.96, 2) - scanY * scanY));

        const yPos = cy + scanY;
        const grad = ctx.createLinearGradient(cx - widthHalf, yPos, cx + widthHalf, yPos);
        grad.addColorStop(0, rgba(2, 0));
        grad.addColorStop(0.2, rgba(1, 0.5 * cur.scan));
        grad.addColorStop(0.5, rgba(0, 0.9 * cur.scan));
        grad.addColorStop(0.8, rgba(1, 0.5 * cur.scan));
        grad.addColorStop(1, rgba(2, 0));

        ctx.beginPath();
        ctx.moveTo(cx - widthHalf, yPos);
        ctx.lineTo(cx + widthHalf, yPos);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.6;
        ctx.stroke();

        // Small indicator tick marks on the scanline edge
        ctx.fillStyle = rgba(0, 0.8 * cur.scan);
        ctx.fillRect(Math.round(cx - widthHalf), Math.round(yPos - 2), 2, 5);
        ctx.fillRect(Math.round(cx + widthHalf - 2), Math.round(yPos - 2), 2, 5);
    }

    function drawDust(
        scale: number,
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
    ) {
        // Volumetric 3D spatial points rotating with the sphere
        const cs = Math.cos(dustAngle);
        const sn = Math.sin(dustAngle);

        for (let i = 0; i < dustN; i++) {
            const x0 = dustX[i] * cs + dustZ[i] * sn;
            const z0 = -dustX[i] * sn + dustZ[i] * cs;
            const y0 = dustY[i];

            const pt = project3D(x0, y0, z0, scale, cosY, sinY, cosX, sinX);
            const flicker = 0.5 + 0.5 * Math.sin(t * 2.5 + dustSeed[i]);
            const a = (0.15 + 0.65 * pt.depth) * flicker * (0.6 + 0.4 * cur.energy) * (0.9 + 0.3 * glow);

            if (a < 0.04) continue;
            ctx.fillStyle = rgba(dustTint[i], clamp(a, 0, 0.9));
            const sz = a > 0.55 && pt.depth > 0.6 ? 2 : 1;
            ctx.fillRect(Math.round(pt.px), Math.round(pt.py), sz, sz);
        }
    }

    /* ---------------------------------------------------------------- frame */

    function frame(now: number) {
        if (!running) return;
        raf = requestAnimationFrame(frame);
        if (!w || !h) {
            last = now;
            return;
        }

        const dt = last ? clamp((now - last) / 1000, 0, 0.05) : 0.016;
        last = now;
        t += dt;

        /* ---- state-specific targets ---- */
        if (state === 'listening') {
            // Receptive acoustic membrane: rings steer forward, micro-waveform ripples
            tgt.scale = 1.01;
            tgt.spin = 0.55;
            tgt.energy = 0.92;
            tgt.vibe = 0.85;
            tgt.faceCam = 0.5;
            tgt.pulseFreq = 1.2;
            tgt.scan = 0;
            tgt.bloom = 1.2;
        } else if (state === 'thinking') {
            // Processing: dignified slow spin, neural computation strobe, gentle scan beam
            tgt.scale = 0.97;
            tgt.spin = 1.15;
            tgt.energy = 0.95;
            tgt.vibe = 0.08;
            tgt.faceCam = 0;
            tgt.pulseFreq = 2.4;
            tgt.scan = 0.85;
            tgt.bloom = 1.12;
        } else if (state === 'speaking') {
            // Vocal resonance: warm expansion waves, radiant bloom
            tgt.scale = 1.03;
            tgt.spin = 0.85;
            tgt.energy = 1.0;
            tgt.vibe = 0.25;
            tgt.faceCam = 0.1;
            tgt.pulseFreq = 1.5;
            tgt.scan = 0;
            tgt.bloom = 1.35;
        } else {
            // Idle: serene majestic gyroscopic tumble, calm breathing
            tgt.scale = 1.0;
            tgt.spin = 1.0;
            tgt.energy = 0.65;
            tgt.vibe = 0;
            tgt.faceCam = 0;
            tgt.pulseFreq = 0.65;
            tgt.scan = 0;
            tgt.bloom = 1.0;
        }

        // Smoothly interpolate all parameters with exponential damping
        const k = 1 - Math.exp(-dt * 3.2);
        cur.scale = lerp(cur.scale, tgt.scale, k);
        cur.spin = lerp(cur.spin, tgt.spin, k);
        cur.energy = lerp(cur.energy, tgt.energy, k);
        cur.vibe = lerp(cur.vibe, tgt.vibe, k);
        cur.faceCam = lerp(cur.faceCam, tgt.faceCam, k);
        cur.pulseFreq = lerp(cur.pulseFreq, tgt.pulseFreq, k);
        cur.scan = lerp(cur.scan, tgt.scan, k);
        cur.bloom = lerp(cur.bloom, tgt.bloom, k);

        // Pointer parallax damping
        const pk = 1 - Math.exp(-dt * 3.8);
        ptr.x = lerp(ptr.x, ptr.tx, pk);
        ptr.y = lerp(ptr.y, ptr.ty, pk);

        // Glow decay
        glow *= Math.exp(-dt * 4.5);

        // In speaking state: emit rhythmic expanding vocal soundwaves
        if (state === 'speaking') {
            vocalTimer -= dt;
            if (vocalTimer <= 0) {
                spawnSoundwave(0.35);
                vocalTimer = 0.52;
                if (Math.random() < 0.4) emitEmbers(2);
            }
        } else {
            vocalTimer = 0.1;
        }

        // Update soundwave expansions
        for (let i = 0; i < soundwaves.length; i++) {
            soundwaves[i].rad += dt * soundwaves[i].speed;
        }

        // Continuous smooth angle integration — NO sudden jumps during state changes
        camYawAngle = (camYawAngle + dt * 0.042 * cur.spin) % TAU;
        dustAngle = (dustAngle + dt * 0.028 * cur.spin) % TAU;
        coreArcAngle = (coreArcAngle + dt * 0.85 * cur.spin) % TAU;
        latAngle = (latAngle + dt * 0.022 * cur.spin) % TAU;

        // Update gimbal ring spin angles
        for (let i = 0; i < gimbalRings.length; i++) {
            const gr = gimbalRings[i];
            gr.angle = (gr.angle + gr.spinSpeed * cur.spin * dt) % TAU;
        }

        // Organic harmonic breathing scale
        const breath = Math.sin(t * TAU * (state === 'thinking' ? 1.4 : 0.65)) * 0.018;
        const scale = Math.max(0.001, cur.scale * (1 + breath));

        // 3D Camera Angles: Yaw & Pitch influenced by continuous yaw and mouse pointer
        const ry = camYawAngle + ptr.x * 0.35;
        const rx = 0.18 + ptr.y * 0.22 + 0.03 * Math.sin(t * 0.08);
        const cosY = Math.cos(ry);
        const sinY = Math.sin(ry);
        const cosX = Math.cos(rx);
        const sinX = Math.sin(rx);

        cx = w / 2 + ptr.x * R * 0.05;
        cy = h / 2 + ptr.y * R * 0.05;

        /* ---- Canvas render pass ---- */
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        ctx.globalCompositeOperation = 'lighter';
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        // 1. Soft atmospheric back-glow
        const haze = Math.max(0, R * 2.4 * scale);
        ctx.globalAlpha = 0.14 + 0.08 * cur.energy + 0.1 * glow;
        ctx.drawImage(sprites[5], cx - haze / 2, cy - haze / 2, haze, haze);
        ctx.globalAlpha = 1;

        // 2. 3D Spherical Tech Cage (Longitudes & Latitudes)
        drawSphericalCage(scale, cosY, sinY, cosX, sinX);

        // 3. Volumetric 3D Particle Cloud
        drawDust(scale, cosY, sinY, cosX, sinX);

        // 4. Concentric Tech Gimbal Rings
        for (let i = 0; i < gimbalRings.length; i++) {
            drawTechGimbalRing(gimbalRings[i], scale, cosY, sinY, cosX, sinX);
        }

        // 5. Central High-Intensity Plasma Arc Reactor
        drawCentralArcReactor(scale);

        // 6. Expanding Vocal / Resonance Soundwaves
        drawSoundwaves();

        // 7. Holographic Scan-Plane (Active during thinking)
        drawScanPlane(scale);

        // 8. Embers
        for (let i = embers.length - 1; i >= 0; i--) {
            const e = embers[i];
            e.life -= dt / e.max;
            if (e.life <= 0) {
                embers.splice(i, 1);
                continue;
            }
            e.x += e.vx * dt;
            e.y += e.vy * dt;
            e.vx *= 1 - 0.7 * dt;
            e.vy *= 1 - 0.7 * dt;
            ctx.globalAlpha = clamp(e.life, 0, 1) * 0.85;
            ctx.fillStyle = rgba(e.tint, 0.9);
            ctx.fillRect(cx + e.x, cy + e.y, 1 + e.life, 1 + e.life);
        }
        ctx.globalAlpha = 1;

        ctx.globalCompositeOperation = 'source-over';
    }

    /* ------------------------------------------------------------------ API */

    const handle: JarvisCoreHandle = {
        setState(next) {
            if (next === state) return;
            state = next;
        },
        pulse(strength = 0.5) {
            // Brightens the core and triggers an expansive vocal soundwave
            glow = clamp(glow + strength * 0.65, 0, 1.2);
            spawnSoundwave(strength);
        },
        setPointer(x, y, inside) {
            ptr.tx = clamp(x, -1.6, 1.6);
            ptr.ty = clamp(y, -1.6, 1.6);
            ptr.inside = inside;
        },
        resize(width, height, nextDpr) {
            w = width;
            h = height;
            dpr = nextDpr;
            R = Math.min(w, h) * 0.42;
            cx = w / 2;
            cy = h / 2;
            canvas.width = Math.max(1, Math.round(w * dpr));
            canvas.height = Math.max(1, Math.round(h * dpr));
            canvas.style.width = `${w}px`;
            canvas.style.height = `${h}px`;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);
            buildRings();
        },
        destroy() {
            running = false;
            if (raf) cancelAnimationFrame(raf);
            raf = 0;
            soundwaves = [];
            embers = [];
        },
    };

    last = 0;
    raf = requestAnimationFrame(frame);
    return handle;
}
