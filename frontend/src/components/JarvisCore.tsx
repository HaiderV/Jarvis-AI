import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import {
    createJarvisCore,
    type CoreState,
    type JarvisCoreHandle,
} from '../core/jarvisCore';

export interface JarvisCoreRef {
    pulse: (strength?: number) => void;
}

interface Props {
    state: CoreState;
    onActivate?: () => void;
    /** small mono caption under the core, e.g. "LISTENING" */
    label?: string;
    hint?: string;
    /** set false for a completely bare core with no text at all */
    showCaption?: boolean;
}

/**
 * Full-bleed core. The canvas fills its parent completely — no frame, no
 * border, no rounded box. Give it a big, open area and the fire fades out
 * into the page on its own.
 */
export const JarvisCore = forwardRef<JarvisCoreRef, Props>(function JarvisCore(
    { state, onActivate, label, hint, showCaption = true },
    ref,
) {
    const hostRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const engineRef = useRef<JarvisCoreHandle | null>(null);

    useImperativeHandle(ref, () => ({
        pulse: (strength?: number) => engineRef.current?.pulse(strength),
    }));

    useEffect(() => {
        const canvas = canvasRef.current;
        const host = hostRef.current;
        if (!canvas || !host) return;

        const engine = createJarvisCore(canvas);
        engineRef.current = engine;

        const fit = () => {
            const rect = host.getBoundingClientRect();
            if (rect.width < 2 || rect.height < 2) return;
            engine.resize(rect.width, rect.height, Math.min(window.devicePixelRatio || 1, 2));
        };
        fit();

        const ro = new ResizeObserver(fit);
        ro.observe(host);

        // pointer drives the sphere's tilt and the plasma's attraction
        const onMove = (event: PointerEvent) => {
            const rect = host.getBoundingClientRect();
            const nx = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            const ny = ((event.clientY - rect.top) / rect.height) * 2 - 1;
            const inside =
                nx > -1.25 && nx < 1.25 && ny > -1.25 && ny < 1.25;
            engine.setPointer(nx, ny, inside);
        };
        const onLeave = () => engine.setPointer(0, 0, false);

        window.addEventListener('pointermove', onMove, { passive: true });
        window.addEventListener('pointerleave', onLeave);
        document.addEventListener('mouseleave', onLeave);

        const onVisibility = () => {
            if (!document.hidden) fit();
        };
        document.addEventListener('visibilitychange', onVisibility);

        return () => {
            ro.disconnect();
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerleave', onLeave);
            document.removeEventListener('mouseleave', onLeave);
            document.removeEventListener('visibilitychange', onVisibility);
            engine.destroy();
            engineRef.current = null;
        };
    }, []);

    useEffect(() => {
        engineRef.current?.setState(state);
    }, [state]);

    return (
        <div className="core" ref={hostRef}>
            <canvas className="core-canvas" ref={canvasRef} aria-hidden="true" />

            <button
                type="button"
                className="core-hit"
                onClick={onActivate}
                aria-label={state === 'listening' ? 'Stop listening' : 'Speak to Jarvis'}
            />

            <div className={`core-caption-group${showCaption ? '' : ' is-hidden'}`}>
                <div className={`core-state ${state}`}>
                    <span className="core-state-dot" />
                    <span>{label ?? state}</span>
                </div>
                {hint ? <p className="core-hint">{hint}</p> : null}
            </div>
        </div>
    );
});
