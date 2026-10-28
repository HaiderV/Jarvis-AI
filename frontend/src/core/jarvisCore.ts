/**
 * jarvisCore.ts — v3
 * ---------------------------------------------------------------------------
 * A sphere woven out of fire.
 *
 * The body is not a cloud of dust: it is ~200 long glowing strands, each one
 * an arc of a great circle wrapped around the sphere, drawn as a thin curved
 * polyline. Where the strands turn edge-on at the silhouette they pile up and
 * the rim lights up on its own, which is exactly how the reference reads.
 *
 *  - 3D: every strand point is a real sphere point, rotated by a matrix and
 *    perspective-projected, so the ball tumbles in space instead of spinning
 *    flat.
 *  - Crisp: the canvas is cleared every frame. No trails, nothing smears.
 *  - No sudden jumps. Every size change is eased; the only rhythm is a slow
 *    breathing curve that never restarts.
 *  - Open: no frame, no cage. Strands fray and fade into the page.
 *
 * States: idle / listening / thinking / speaking.
 */

export type CoreState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface JarvisCoreHandle {
    setState(next: CoreState): void;
    /** brightens the core briefly — never changes its size */
    pulse(strength?: number): void;
    setPointer(x: number, y: number, inside: boolean): void;
    resize(width: number, height: number, dpr: number): void;
    destroy(): void;
}

const TAU = Math.PI * 2;
const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/* ------------------------------------------------------------------ noise */

function hash1(n: number): number {
    const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
}

function vnoise(x: number, seed: number): number {
    const i = Math.floor(x);
    const f = x - i;
    const a = hash1(i + seed * 13.13);
    const b = hash1(i + 1 + seed * 13.13);
    const u = f * f * (3 - 2 * f);
    return a + (b - a) * u;
}

function fbm(x: number, seed: number): number {
    return (
        vnoise(x, seed) * 0.62 +
        vnoise(x * 2.17, seed + 3.7) * 0.26 +
        vnoise(x * 4.41, seed + 9.1) * 0.12
    );
}

/* ---------------------------------------------------------------- palette */

const PALETTE: [number, number, number][] = [
    [255, 247, 218], // 0 white hot
    [255, 226, 152], // 1 pale gold
    [255, 197, 84], // 2 gold
    [255, 158, 38], // 3 amber
    [233, 108, 14], // 4 orange
    [170, 56, 4], // 5 deep ember
];

const rgba = (tint: number, a: number) => {
    const c = PALETTE[tint];
    return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
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
    grad.addColorStop(0.16 * tight, `rgba(${r},${g},${b},0.72)`);
    grad.addColorStop(0.42 * tight, `rgba(${r},${g},${b},0.26)`);
    grad.addColorStop(0.72 * tight, `rgba(${r},${g},${b},0.07)`);
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
    c.fillStyle = grad;
    c.fillRect(0, 0, size, size);
    return cv;
}

/* ------------------------------------------------------------------ types */

interface Strand {
    ux: number;
    uy: number;
    uz: number;
    vx: number;
    vy: number;
    vz: number;
    a0: number;
    len: number;
    rad: number;
    width: number;
    tint: number;
    seed: number;
    wob: number;
    phase: number;
    tail: number; // >0 : the strand frays past the surface
    gain: number;
    dash: boolean;
}

interface Tangle {
    rad: number;
    a0: number;
    len: number;
    tilt: number;
    seed: number;
    width: number;
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

const STEPS = 26; // points per strand
const CHUNKS = 2; // alpha bands per strand

/* ----------------------------------------------------------------- engine */

export function createJarvisCore(canvas: HTMLCanvasElement): JarvisCoreHandle {
    const ctx = canvas.getContext('2d', { alpha: true })!;
    const sprites = PALETTE.map((_, i) => makeSprite(i, i === 0 ? 0.7 : 1));

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

    const cur = { scale: 1, spin: 1, energy: 0.6, rim: 0.5, corona: 1, scan: 0 };
    const tgt = { scale: 1, spin: 1, energy: 0.6, rim: 0.5, corona: 1, scan: 0 };

    const ptr = { x: 0, y: 0, tx: 0, ty: 0, inside: false };

    let glow = 0; // brief brightness lift from pulse(), decays fast
    let surgeT = 1.4 + Math.random() * 3;
    let surge = 0;

    let strands: Strand[] = [];
    let tangle: Tangle[] = [];
    let dustX: Float32Array = new Float32Array(0);
    let dustY: Float32Array = new Float32Array(0);
    let dustZ: Float32Array = new Float32Array(0);
    let dustSeed: Float32Array = new Float32Array(0);
    let dustTint: Uint8Array = new Uint8Array(0);
    let dustN = 0;

    let embers: Ember[] = [];

    /* ---------------------------------------------------------- population */

    function build() {
        const area = w * h;

        strands = [];
        const count = Math.round(clamp(area / 760, 200, 520));
        for (let i = 0; i < count; i++) {
            // a random great circle: normal n, plus an orthonormal basis u, v
            const nz = 2 * Math.random() - 1;
            const na = Math.random() * TAU;
            const nr = Math.sqrt(Math.max(0, 1 - nz * nz));
            const nx = nr * Math.cos(na);
            const ny = nr * Math.sin(na);

            // u = normalise(any vector not parallel to n)
            let ux = -ny;
            let uy = nx;
            let uz = 0;
            if (Math.abs(ux) + Math.abs(uy) < 1e-4) {
                ux = 1;
                uy = 0;
            }
            const ul = Math.hypot(ux, uy, uz) || 1;
            ux /= ul;
            uy /= ul;
            uz /= ul;

            // v = n × u
            const vx = ny * uz - nz * uy;
            const vy = nz * ux - nx * uz;
            const vz = nx * uy - ny * ux;

            const shell = Math.random();
            const rad = shell < 0.55 ? 0.9 + Math.random() * 0.14 : 0.62 + Math.random() * 0.3;

            strands.push({
                ux,
                uy,
                uz,
                vx,
                vy,
                vz,
                a0: Math.random() * TAU,
                len: 1.6 + Math.random() * 4.2,
                rad,
                width: 0.45 + Math.pow(Math.random(), 2) * 1.9,
                tint:
                    Math.random() < 0.12
                        ? 1
                        : Math.random() < 0.42
                            ? 2
                            : Math.random() < 0.8
                                ? 3
                                : 4,
                seed: Math.random() * 100,
                wob: 0.02 + Math.random() * 0.05,
                phase: (Math.random() - 0.5) * 0.5,
                tail: Math.random() < 0.22 ? 1.12 + Math.random() * 0.28 : 0,
                gain: 0.45 + Math.pow(Math.random(), 1.6) * 1.35,
                dash: Math.random() < 0.38,
            });
        }

        // the bright knot at the middle: short chaotic arcs
        tangle = [];
        for (let i = 0; i < 54; i++) {
            tangle.push({
                rad: 0.04 + Math.random() * 0.24,
                a0: Math.random() * TAU,
                len: 0.5 + Math.random() * 2.2,
                tilt: (Math.random() - 0.5) * 1.5,
                seed: Math.random() * 50,
                width: 0.6 + Math.random() * 0.9,
            });
        }

        // grain: fine points sprinkled through the volume
        dustN = Math.round(clamp(area / 170, 1100, 3600));
        dustX = new Float32Array(dustN);
        dustY = new Float32Array(dustN);
        dustZ = new Float32Array(dustN);
        dustSeed = new Float32Array(dustN);
        dustTint = new Uint8Array(dustN);
        for (let i = 0; i < dustN; i++) {
            const ph = Math.acos(2 * Math.random() - 1);
            const th = Math.random() * TAU;
            const rad = Math.pow(Math.random(), 0.55);
            dustX[i] = Math.sin(ph) * Math.cos(th) * rad;
            dustY[i] = Math.cos(ph) * rad;
            dustZ[i] = Math.sin(ph) * Math.sin(th) * rad;
            dustSeed[i] = Math.random() * 200;
            dustTint[i] = rad < 0.3 ? (Math.random() < 0.5 ? 0 : 1) : rad < 0.75 ? 2 : 3;
        }

        embers = [];
    }

    function emitEmbers(n: number, power: number) {
        for (let i = 0; i < n; i++) {
            const a = Math.random() * TAU;
            const r0 = R * (0.5 + Math.random() * 0.5);
            const sp = R * (0.12 + Math.random() * 0.32) * power;
            embers.push({
                x: Math.cos(a) * r0,
                y: Math.sin(a) * r0,
                vx: Math.cos(a) * sp,
                vy: Math.sin(a) * sp,
                life: 1,
                max: 1 + Math.random() * 1.6,
                size: 0.8 + Math.random() * 1.4,
                tint: 2 + ((Math.random() * 4) | 0),
            });
        }
    }

    /* -------------------------------------------------------------- drawing */

    function drawStrands(
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
        scale: number,
    ) {
        const energy = cur.energy;

        for (let i = 0; i < strands.length; i++) {
            const s = strands[i];

            // rotate the strand's basis once — the circle itself stays cheap
            const ux1 = s.ux * cosY + s.uz * sinY;
            const uz1 = -s.ux * sinY + s.uz * cosY;
            const uy1 = s.uy * cosX - uz1 * sinX;
            const uz2 = s.uy * sinX + uz1 * cosX;

            const vx1 = s.vx * cosY + s.vz * sinY;
            const vz1 = -s.vx * sinY + s.vz * cosY;
            const vy1 = s.vy * cosX - vz1 * sinX;
            const vz2 = s.vy * sinX + vz1 * cosX;

            const drift = t * s.phase * 0.08;

            for (let c = 0; c < CHUNKS; c++) {
                const k0 = (c / CHUNKS) * STEPS;
                const k1 = ((c + 1) / CHUNKS) * STEPS;

                let midZ = 0;
                let started = false;

                ctx.beginPath();
                for (let k = k0; k <= k1; k++) {
                    const f = k / STEPS;
                    const th = s.a0 + f * s.len + drift;
                    const cs = Math.cos(th);
                    const sn = Math.sin(th);

                    const X = ux1 * cs + vx1 * sn;
                    const Y = uy1 * cs + vy1 * sn;
                    const Z = uz2 * cs + vz2 * sn;

                    const fray =
                        s.tail > 0 && f > 0.86 ? 1 + (f - 0.86) * (s.tail - 1) * 4.5 : 1;
                    const wob = 1 + Math.sin(th * 2.6 + t * 0.55 + s.seed) * s.wob;
                    const rr = s.rad * wob * fray * scale;

                    const persp = 2.6 / (2.6 + Z * 0.85);
                    const px = cx + X * rr * R * persp;
                    const py = cy + Y * rr * R * persp;

                    if (!started) {
                        ctx.moveTo(px, py);
                        started = true;
                    } else {
                        ctx.lineTo(px, py);
                    }
                    midZ += Z;
                }

                midZ /= k1 - k0 + 1;
                const depth = clamp((midZ + 1) / 2, 0, 1);
                // edge-on strands (small |Z|) are the bright rim
                const limb = Math.pow(1 - Math.abs(midZ), 1.7);
                const a =
                    (0.07 + 0.62 * Math.pow(depth, 1.4)) *
                    (0.25 + 1.7 * limb) *
                    s.gain *
                    (0.55 + 0.6 * energy) *
                    (0.92 + 0.45 * surge + 0.22 * glow);

                if (a < 0.012) continue;

                const lw = s.width * (0.6 + depth * 0.7);

                // wide, faint halo first — this is what makes them glow
                ctx.strokeStyle = rgba(s.tint, clamp(a * 0.14, 0, 0.4));
                ctx.lineWidth = lw * 3.4;
                ctx.stroke();

                // then the filament itself — some of them read as beads, like the
                // reference, where the strands break up into dashes of light
                ctx.strokeStyle = rgba(s.tint, clamp(a, 0, 0.7));
                ctx.lineWidth = lw;
                if (s.dash) ctx.setLineDash([1.4 + s.width, 2.4 + s.width * 1.6]);
                ctx.stroke();
                if (s.dash) ctx.setLineDash([]);
            }
        }
    }

    function drawDust(
        cosY: number,
        sinY: number,
        cosX: number,
        sinX: number,
        scale: number,
    ) {
        const mx = w / 2 + ptr.x * (w / 2) * 0.9;
        const my = h / 2 + ptr.y * (h / 2) * 0.9;
        const pullR2 = R * R * 0.3;
        const spin = t * 0.06 * cur.spin;
        const cs = Math.cos(spin);
        const sn = Math.sin(spin);

        for (let i = 0; i < dustN; i++) {
            // spin the grain around the sphere's own axis, then into view space
            const x0 = dustX[i] * cs + dustZ[i] * sn;
            const z0 = -dustX[i] * sn + dustZ[i] * cs;
            const y0 = dustY[i];

            const x1 = x0 * cosY + z0 * sinY;
            const z1 = -x0 * sinY + z0 * cosY;
            const y1 = y0 * cosX - z1 * sinX;
            const z2 = y0 * sinX + z1 * cosX;

            const persp = 2.6 / (2.6 + z2 * 0.85);
            const depth = clamp((z2 + 1) / 2, 0, 1);
            const rad = scale * (1 + Math.sin(t * 0.4 + dustSeed[i]) * 0.03);

            let px = cx + x1 * rad * R * persp;
            let py = cy + y1 * rad * R * persp;

            if (ptr.inside) {
                const dx = mx - px;
                const dy = my - py;
                const d2 = dx * dx + dy * dy;
                if (d2 < pullR2) {
                    const f = 1 - d2 / pullR2;
                    px += dx * f * 0.16;
                    py += dy * f * 0.16;
                }
            }

            const flick = 0.5 + 0.5 * Math.sin(t * (0.9 + dustSeed[i] * 0.02) + dustSeed[i]);
            let a =
                (0.1 + 0.6 * Math.pow(depth, 1.4)) *
                flick *
                (0.5 + 0.6 * cur.energy) *
                (0.85 + 0.45 * surge + 0.2 * glow);

            if (ptr.inside) {
                const dx = mx - px;
                const dy = my - py;
                const d2 = dx * dx + dy * dy;
                if (d2 < pullR2) a *= 1 + (1 - d2 / pullR2) * 0.8;
            }
            if (a < 0.02) continue;

            ctx.fillStyle = rgba(dustTint[i], clamp(a, 0, 0.9));
            const sz = a > 0.5 ? 2 : 1;
            ctx.fillRect(Math.round(px), Math.round(py), sz, sz);
        }
    }

    function drawRim(scale: number) {
        // the silhouette catching light: short bright arcs, full of gaps
        const spin = t * cur.rim * 0.5;
        for (let tier = 0; tier < 3; tier++) {
            ctx.beginPath();
            let any = false;
            for (let i = 0; i < 132; i++) {
                const n = fbm(i * 0.31 + 1.1, 4.2);
                const tIdx = Math.min(2, Math.floor(n * 3));
                if (tIdx !== tier) continue;
                if (fbm(i * 0.19 + 7.7, 9.3) < 0.3) continue;

                const a0 = (i / 132) * TAU + spin + n * 0.12;
                const dash = (TAU / 132) * (0.2 + n * 0.8);
                const rad = R * scale * (0.99 + (n - 0.5) * 0.05);

                ctx.moveTo(cx + Math.cos(a0) * rad, cy + Math.sin(a0) * rad * 0.985);
                ctx.arc(cx, cy, rad, a0, a0 + dash);
                any = true;
            }
            if (!any) continue;
            ctx.strokeStyle = rgba(2, ((tier + 1) / 3) * 0.6 * (0.45 + 0.8 * cur.energy));
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }

    function drawTangle(scale: number) {
        for (let i = 0; i < tangle.length; i++) {
            const g = tangle[i];
            const rot = t * (0.5 + (g.seed % 3) * 0.35) + g.seed;
            const wob = Math.sin(t * 0.9 + g.seed) * 0.06;

            const rx = R * (g.rad + wob) * scale;
            const squash = 0.35 + Math.abs(Math.sin(g.tilt)) * 0.65;

            const a0 = g.a0 + rot;
            const n = fbm(t * 0.6 + g.seed, 3.9);
            const a = (0.22 + 0.72 * n) * (0.6 + 0.5 * cur.energy + 0.5 * glow);

            ctx.strokeStyle = rgba(i % 4 === 0 ? 0 : i % 3 === 0 ? 1 : 2, clamp(a, 0, 0.85));
            ctx.lineWidth = g.width;
            ctx.beginPath();
            ctx.ellipse(cx, cy, rx, rx * squash, g.tilt + rot * 0.4, a0, a0 + g.len);
            ctx.stroke();
        }
    }

    function drawKnot(scale: number) {
        const breathe = 1 + 0.03 * Math.sin(t * 0.6);
        const pulse = 0.55 + 0.45 * fbm(t * 0.8, 3.3) + 0.35 * glow;

        const size = R * 0.42 * scale * breathe;
        ctx.globalAlpha = clamp((0.4 + 0.24 * cur.energy) * pulse, 0, 1);
        ctx.drawImage(sprites[1], cx - size / 2, cy - size / 2, size, size);

        const hot = R * 0.14 * scale * breathe;
        ctx.globalAlpha = clamp(0.75 * pulse, 0, 1);
        ctx.drawImage(sprites[0], cx - hot / 2, cy - hot / 2, hot, hot);

        const flareW = R * 1.7 * scale * (0.9 + 0.15 * pulse);
        const flareH = R * 0.028 * scale;
        ctx.globalAlpha = clamp(0.12 + 0.1 * cur.energy + 0.1 * glow, 0, 1);
        ctx.drawImage(sprites[1], cx - flareW / 2, cy - flareH / 2, flareW, flareH);

        ctx.globalAlpha = 1;
    }

    function drawScan(scale: number) {
        if (cur.scan < 0.02) return;
        const pos = (fbm(t * 0.28, 11.2) - 0.5) * 1.5;
        const yy = cy + pos * R * 0.85 * scale;
        const halfW = R * 0.95 * scale * Math.sqrt(Math.max(0, 1 - pos * pos * 0.7));

        const grad = ctx.createLinearGradient(cx - halfW, yy, cx + halfW, yy);
        grad.addColorStop(0, rgba(2, 0));
        grad.addColorStop(0.5, rgba(2, 0.45 * cur.scan));
        grad.addColorStop(1, rgba(2, 0));
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(cx - halfW, yy);
        ctx.lineTo(cx + halfW, yy);
        ctx.stroke();
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

        /* ---- state targets ---- */
        if (state === 'listening') {
            tgt.scale = 0.93;
            tgt.spin = 1.6;
            tgt.energy = 0.92;
            tgt.rim = 1.15;
            tgt.corona = 0.5;
            tgt.scan = 0;
        } else if (state === 'thinking') {
            tgt.scale = 0.97;
            tgt.spin = 2.4;
            tgt.energy = 0.8;
            tgt.rim = 2.1;
            tgt.corona = 0.7;
            tgt.scan = 1;
        } else if (state === 'speaking') {
            tgt.scale = 1;
            tgt.spin = 0.9;
            tgt.energy = 1;
            tgt.rim = 0.7;
            tgt.corona = 1.2;
            tgt.scan = 0;
        } else {
            tgt.scale = 1;
            tgt.spin = 1;
            tgt.energy = 0.62;
            tgt.rim = 0.5;
            tgt.corona = 1;
            tgt.scan = 0;
        }

        // everything is eased — no state change ever snaps the size
        const k = 1 - Math.exp(-dt * 2.6);
        cur.scale = lerp(cur.scale, tgt.scale, k);
        cur.spin = lerp(cur.spin, tgt.spin, k);
        cur.energy = lerp(cur.energy, tgt.energy, k);
        cur.rim = lerp(cur.rim, tgt.rim, k);
        cur.corona = lerp(cur.corona, tgt.corona, k);
        cur.scan = lerp(cur.scan, tgt.scan, k);

        const pk = 1 - Math.exp(-dt * 3.6);
        ptr.x = lerp(ptr.x, ptr.tx, pk);
        ptr.y = lerp(ptr.y, ptr.ty, pk);

        glow *= Math.exp(-dt * 5.5);

        /* ---- rare, non-repeating flares: brightness only ---- */
        surgeT -= dt;
        if (surgeT <= 0) {
            surge = 1;
            surgeT = 1.6 + Math.random() * 5.4;
            if (Math.random() < 0.5) emitEmbers(4, 0.8);
        }
        surge *= Math.exp(-dt * 1.9);

        /* ---- slow breathing; never a jump ---- */
        const breath = state === 'speaking' ? Math.sin(t * 1.7) : 0;
        const scale = cur.scale * (1 + 0.022 * breath);

        const ry = t * 0.13 * cur.spin + ptr.x * 0.55;
        const rx = 0.24 + ptr.y * 0.4 + 0.09 * Math.sin(t * 0.06);
        const cosY = Math.cos(ry);
        const sinY = Math.sin(ry);
        const cosX = Math.cos(rx);
        const sinX = Math.sin(rx);

        cx = w / 2 + ptr.x * R * 0.04;
        cy = h / 2 + ptr.y * R * 0.04;

        /* ---- draw ---- */
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        ctx.globalCompositeOperation = 'lighter';
        ctx.lineCap = 'round';

        // body of light behind everything, so the strands sit inside fire
        const haze = R * 2.2 * scale;
        ctx.globalAlpha = 0.13 + 0.06 * cur.energy + 0.05 * surge;
        ctx.drawImage(sprites[4], cx - haze / 2, cy - haze / 2, haze, haze);
        const mid = R * 1.1 * scale;
        ctx.globalAlpha = 0.11 + 0.05 * cur.energy;
        ctx.drawImage(sprites[3], cx - mid / 2, cy - mid / 2, mid, mid);
        ctx.globalAlpha = 1;

        // loose embers drifting outside the sphere
        const coronaCount = Math.min(150, Math.round(strands.length * 0.5));
        for (let i = 0; i < coronaCount; i++) {
            const seed = i * 3.77;
            const th = hash1(seed + 1.7) * TAU + t * (0.02 + hash1(seed) * 0.05);
            const ph = Math.acos(2 * hash1(seed + 4.2) - 1);
            const rad = R * (1.05 + hash1(seed + 8.8) * 0.4) * scale;

            const x0 = Math.sin(ph) * Math.cos(th);
            const y0 = Math.cos(ph);
            const z0 = Math.sin(ph) * Math.sin(th);
            const x1 = x0 * cosY + z0 * sinY;
            const z1 = -x0 * sinY + z0 * cosY;
            const y1 = y0 * cosX - z1 * sinX;

            const flick = fbm(t * (0.5 + hash1(seed + 2)) + seed, seed * 0.5);
            const a = flick * 0.42 * cur.corona;
            if (a < 0.03) continue;

            ctx.fillStyle = rgba(flick > 0.72 ? 2 : 4, clamp(a, 0, 0.8));
            ctx.fillRect(Math.round(cx + x1 * rad), Math.round(cy + y1 * rad), 1, 1);
        }

        drawStrands(cosY, sinY, cosX, sinX, scale);
        drawDust(cosY, sinY, cosX, sinX, scale);
        drawRim(scale);
        drawTangle(scale);
        drawKnot(scale);

        // embers
        for (let i = embers.length - 1; i >= 0; i--) {
            const e = embers[i];
            e.life -= dt / e.max;
            if (e.life <= 0) {
                embers.splice(i, 1);
                continue;
            }
            e.x += e.vx * dt;
            e.y += e.vy * dt;
            e.vx *= 1 - 0.9 * dt;
            e.vy *= 1 - 0.9 * dt;
            ctx.globalAlpha = clamp(e.life, 0, 1) * 0.9;
            ctx.fillStyle = rgba(e.tint, 0.85);
            ctx.fillRect(cx + e.x, cy + e.y, 1 + e.life, 1 + e.life);
        }
        ctx.globalAlpha = 1;

        drawScan(scale);
        ctx.globalCompositeOperation = 'source-over';
    }

    /* ------------------------------------------------------------------ API */

    const handle: JarvisCoreHandle = {
        setState(next) {
            if (next === state) return;
            state = next;
        },
        pulse(strength = 0.5) {
            // a breath of extra light only — the size never jumps
            glow = clamp(glow + strength * 0.55, 0, 0.75);
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
            embers = [];
            build();
        },
        destroy() {
            running = false;
            if (raf) cancelAnimationFrame(raf);
            raf = 0;
            embers = [];
        },
    };

    last = 0;
    raf = requestAnimationFrame(frame);
    return handle;
}
