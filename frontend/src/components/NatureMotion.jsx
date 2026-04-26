import { Fragment } from 'react';

const LEAF_CONFIG = [
  { x: 6, delay: 0.1, dur: 11, drift: -35, size: 10, rot: 18 },
  { x: 14, delay: 1.3, dur: 13, drift: 40, size: 12, rot: -26 },
  { x: 22, delay: 0.6, dur: 9.5, drift: -24, size: 9, rot: 32 },
  { x: 30, delay: 2.1, dur: 12.2, drift: 28, size: 11, rot: -12 },
  { x: 38, delay: 0.9, dur: 10.7, drift: -30, size: 8, rot: 24 },
  { x: 47, delay: 2.9, dur: 14.5, drift: 44, size: 13, rot: -18 },
  { x: 55, delay: 1.8, dur: 9.9, drift: -22, size: 10, rot: 36 },
  { x: 63, delay: 3.2, dur: 11.6, drift: 30, size: 9, rot: -30 },
  { x: 71, delay: 2.5, dur: 12.9, drift: -38, size: 12, rot: 20 },
  { x: 79, delay: 0.4, dur: 9.4, drift: 24, size: 8, rot: -22 },
  { x: 87, delay: 1.5, dur: 13.4, drift: -28, size: 11, rot: 28 },
  { x: 94, delay: 2.8, dur: 10.3, drift: 18, size: 9, rot: -15 },
  { x: 11, delay: 0.2, dur: 8.8, drift: 20, size: 8, rot: 22 },
  { x: 19, delay: 0.9, dur: 10.1, drift: -18, size: 10, rot: -28 },
  { x: 28, delay: 1.4, dur: 9.2, drift: 26, size: 11, rot: 14 },
  { x: 36, delay: 2.4, dur: 8.6, drift: -20, size: 9, rot: -34 },
  { x: 44, delay: 0.5, dur: 9.6, drift: 22, size: 8, rot: 18 },
  { x: 52, delay: 1.7, dur: 10.4, drift: -26, size: 12, rot: -21 },
  { x: 60, delay: 2.3, dur: 8.4, drift: 21, size: 9, rot: 32 },
  { x: 68, delay: 1.1, dur: 9.9, drift: -24, size: 10, rot: -16 },
  { x: 76, delay: 2.6, dur: 10.2, drift: 30, size: 11, rot: 20 },
  { x: 84, delay: 0.7, dur: 8.9, drift: -18, size: 9, rot: -27 },
  { x: 92, delay: 1.9, dur: 9.7, drift: 24, size: 10, rot: 13 },
];

export default function NatureMotion() {
  return (
    <div className="nature-overlay" aria-hidden="true">
      <div className="vines">
        <span className="vine vine-left" />
        <span className="vine vine-right" />
      </div>

      <div className="leaf-field">
        {LEAF_CONFIG.map((leaf, idx) => (
          <Fragment key={`leaf-group-${idx}`}>
            <span
              className="leaf-fall"
              style={{
                '--leaf-x': `${leaf.x}%`,
                '--leaf-delay': `${leaf.delay}s`,
                '--leaf-dur': `${leaf.dur}s`,
                '--leaf-drift': `${leaf.drift}px`,
                '--leaf-size': `${leaf.size}px`,
                '--leaf-rot': `${leaf.rot}deg`,
              }}
            />
            <span
              className="leaf-fall leaf-fall-secondary"
              style={{
                '--leaf-x': `${Math.max(2, Math.min(98, leaf.x + (idx % 2 === 0 ? 2.8 : -2.8)))}%`,
                '--leaf-delay': `${leaf.delay + 0.45}s`,
                '--leaf-dur': `${Math.max(7.8, leaf.dur - 0.7)}s`,
                '--leaf-drift': `${leaf.drift * -0.75}px`,
                '--leaf-size': `${Math.max(7, leaf.size - 1)}px`,
                '--leaf-rot': `${leaf.rot * -1}deg`,
              }}
            />
          </Fragment>
        ))}
      </div>

      <div className="sapling-growth">
        <span className="sapling-soil" />
        <span className="sapling-stem" />
        <span className="sapling-leaf sapling-leaf-left" />
        <span className="sapling-leaf sapling-leaf-right" />
      </div>
    </div>
  );
}
