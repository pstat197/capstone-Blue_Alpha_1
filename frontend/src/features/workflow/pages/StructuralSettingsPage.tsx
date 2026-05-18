import { useMemo, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import { structuralAssumptions, structuralSettingsStorageKey } from "../data/mockWorkflow";

type StructuralProfile = {
  alphaM: number;
  ecM: number;
  slopeM: number;
  maxLag: number;
};

type SliderConfig = {
  key: keyof StructuralProfile;
  label: string;
  description: string;
  min: number;
  max: number;
  step: number;
  valueFormatter: (value: number) => string;
};

const defaultProfile: StructuralProfile = {
  alphaM: structuralAssumptions.alphaM,
  ecM: structuralAssumptions.ecM,
  slopeM: structuralAssumptions.slopeM,
  maxLag: structuralAssumptions.maxLag,
};

const sliderConfigs: SliderConfig[] = [
  {
    key: "alphaM",
    label: "Alpha / Adstock Memory",
    description: "Controls how quickly carryover decays.",
    min: 0,
    max: 1,
    step: 0.01,
    valueFormatter: (value) => value.toFixed(2),
  },
  {
    key: "ecM",
    label: "EC Midpoint",
    description: "Spend index where response hits 50%.",
    min: 0,
    max: 3,
    step: 0.01,
    valueFormatter: (value) => value.toFixed(2),
  },
  {
    key: "slopeM",
    label: "Response Slope",
    description: "How steeply response rises around midpoint.",
    min: 0.2,
    max: 3,
    step: 0.01,
    valueFormatter: (value) => value.toFixed(2),
  },
  {
    key: "maxLag",
    label: "Max Lag",
    description: "Maximum periods carryover can persist.",
    min: 1,
    max: 8,
    step: 1,
    valueFormatter: (value) => String(Math.round(value)),
  },
];

function readStoredProfile(): StructuralProfile {
  const stored = window.localStorage.getItem(structuralSettingsStorageKey);
  if (!stored) {
    return defaultProfile;
  }

  try {
    const parsed = JSON.parse(stored) as Partial<StructuralProfile>;
    return {
      alphaM: clampNumber(parsed.alphaM, 0, 1, defaultProfile.alphaM),
      ecM: clampNumber(parsed.ecM, 0, 3, defaultProfile.ecM),
      slopeM: clampNumber(parsed.slopeM, 0.2, 3, defaultProfile.slopeM),
      maxLag: Math.round(clampNumber(parsed.maxLag, 1, 8, defaultProfile.maxLag)),
    };
  } catch {
    return defaultProfile;
  }
}

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function writeStoredProfile(profile: StructuralProfile) {
  window.localStorage.setItem(structuralSettingsStorageKey, JSON.stringify(profile));
}

function hillResponse(spendIndex: number, ec: number, slope: number) {
  if (spendIndex <= 0) {
    return 0;
  }
  const safeEc = Math.max(ec, 0.01);
  const spendPower = Math.pow(spendIndex, slope);
  return spendPower / (Math.pow(safeEc, slope) + spendPower);
}

function makeResponsePoints(ec: number, slope: number) {
  return Array.from({ length: 61 }, (_, index) => {
    const spend = (index / 60) * 3;
    return {
      x: spend / 3,
      y: hillResponse(spend, ec, slope),
    };
  });
}

function calcLagWeights(alpha: number, maxLag: number) {
  return Array.from({ length: maxLag + 1 }, (_, lag) => Math.pow(alpha, lag));
}

function calcReadout(profile: StructuralProfile) {
  const weights = calcLagWeights(profile.alphaM, profile.maxLag);
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const immediateShare = total ? weights[0] / total : 1;
  const avgLag = total ? weights.reduce((sum, weight, lag) => sum + weight * lag, 0) / total : 0;
  const halfLife = profile.alphaM > 0 && profile.alphaM < 1 ? Math.log(0.5) / Math.log(profile.alphaM) : 0;

  return {
    immediateShare,
    carryoverShare: 1 - immediateShare,
    avgLag,
    halfLife,
  };
}

function SliderCard({
  config,
  value,
  onChange,
}: {
  config: SliderConfig;
  value: number;
  onChange: (value: number) => void;
}) {
  const handleInput = (value: string) => {
    onChange(config.key === "maxLag" ? Math.round(Number(value)) : Number(value));
  };

  return (
    <div className="structural-slider-card">
      <div className="structural-slider-heading">
        <div>
          <h3>{config.label}</h3>
          <p>{config.description}</p>
        </div>
        <span className="structural-value-pill">{config.valueFormatter(value)}</span>
      </div>
      <input
        aria-label={config.label}
        max={config.max}
        min={config.min}
        onChange={(event) => handleInput(event.target.value)}
        onInput={(event) => handleInput(event.currentTarget.value)}
        step={config.step}
        type="range"
        value={value}
      />
      <div className="structural-ticks">
        <span>{config.valueFormatter(config.min)}</span>
        <span>{config.valueFormatter(config.max)}</span>
      </div>
    </div>
  );
}

function ChartShell({
  title,
  subtitle,
  children,
  note,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  note: string;
}) {
  return (
    <article className="structural-chart-card">
      <h3>{title}</h3>
      <p>{subtitle}</p>
      <div className="structural-chart-frame">{children}</div>
      <div className="structural-chart-note">
        <span aria-hidden="true">i</span>
        <p>{note}</p>
      </div>
    </article>
  );
}

function AxisGrid() {
  return (
    <>
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
        <line className="chart-grid-line" key={tick} x1="34" x2="252" y1={20 + tick * 150} y2={20 + tick * 150} />
      ))}
      <line className="chart-axis" x1="34" x2="252" y1="170" y2="170" />
      <line className="chart-axis" x1="34" x2="34" y1="20" y2="170" />
      <text className="chart-label" x="8" y="24">100%</text>
      <text className="chart-label" x="15" y="173">0%</text>
    </>
  );
}

function AdstockChart({ profile }: { profile: StructuralProfile }) {
  const points = Array.from({ length: profile.maxLag + 1 }, (_, lag) => ({
    lag,
    weight: Math.pow(profile.alphaM, lag),
  }));
  const pathPoints = points.map((point) => ({
    x: profile.maxLag === 0 ? 0 : point.lag / profile.maxLag,
    y: point.weight,
  }));
  const linePath = pathPoints.map((point, index) => `${index === 0 ? "M" : "L"} ${(34 + point.x * 218).toFixed(2)} ${(170 - point.y * 150).toFixed(2)}`).join(" ");
  const areaPath = `${linePath} L 252 170 L 34 170 Z`;

  return (
    <svg className="structural-chart" role="img" viewBox="0 0 280 205" aria-label="Adstock memory curve">
      <AxisGrid />
      <path className="chart-area-fill" d={areaPath} />
      <path className="chart-line chart-line--blue" d={linePath} />
      {points.map((point) => (
        <g key={point.lag}>
          <circle className="chart-dot chart-dot--blue" cx={34 + (point.lag / profile.maxLag) * 218} cy={170 - point.weight * 150} r="4" />
          <text className="chart-label" x={29 + (point.lag / profile.maxLag) * 218} y="195">L{point.lag}</text>
        </g>
      ))}
    </svg>
  );
}

function MidpointChart({ profile }: { profile: StructuralProfile }) {
  const path = makeResponsePoints(profile.ecM, profile.slopeM)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${(34 + point.x * 218).toFixed(2)} ${(170 - point.y * 150).toFixed(2)}`)
    .join(" ");
  const markerX = 34 + (profile.ecM / 3) * 218;
  const markerY = 170 - hillResponse(profile.ecM, profile.ecM, profile.slopeM) * 150;

  return (
    <svg className="structural-chart" role="img" viewBox="0 0 280 205" aria-label="Midpoint effect response curve">
      <AxisGrid />
      <path className="chart-area-fill chart-area-fill--green" d={`${path} L 252 170 L 34 170 Z`} />
      <path className="chart-line chart-line--green" d={path} />
      <line className="chart-marker" x1={markerX} x2={markerX} y1="20" y2="170" />
      <circle className="chart-dot chart-dot--green" cx={markerX} cy={markerY} r="4.5" />
      <text className="chart-marker-label" x={Math.min(205, markerX + 8)} y="35">ec = {profile.ecM.toFixed(2)}</text>
      <text className="chart-label" x="32" y="195">0</text>
      <text className="chart-label" x="247" y="195">3</text>
    </svg>
  );
}

function SlopeChart({ profile }: { profile: StructuralProfile }) {
  const gentlerPath = makeResponsePoints(profile.ecM, 0.6)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${(34 + point.x * 218).toFixed(2)} ${(170 - point.y * 150).toFixed(2)}`)
    .join(" ");
  const currentPath = makeResponsePoints(profile.ecM, profile.slopeM)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${(34 + point.x * 218).toFixed(2)} ${(170 - point.y * 150).toFixed(2)}`)
    .join(" ");
  const steeperPath = makeResponsePoints(profile.ecM, 2)
    .map((point, index) => `${index === 0 ? "M" : "L"} ${(34 + point.x * 218).toFixed(2)} ${(170 - point.y * 150).toFixed(2)}`)
    .join(" ");

  return (
    <svg className="structural-chart" role="img" viewBox="0 0 280 205" aria-label="Slope sensitivity comparison">
      <AxisGrid />
      <path className="chart-line chart-line--muted" d={gentlerPath} />
      <path className="chart-line chart-line--purple" d={steeperPath} />
      <path className="chart-line chart-line--green chart-line--strong" d={currentPath} />
      <text className="chart-legend" x="44" y="15">Gentler</text>
      <text className="chart-legend chart-legend--current" x="115" y="15">Current {profile.slopeM.toFixed(2)}</text>
      <text className="chart-legend chart-legend--purple" x="206" y="15">Steeper</text>
    </svg>
  );
}

function MaxLagChart({ profile }: { profile: StructuralProfile }) {
  const weights = Array.from({ length: 9 }, (_, lag) => ({
    lag,
    weight: lag <= profile.maxLag ? Math.pow(profile.alphaM, lag) : 0,
    active: lag <= profile.maxLag,
  }));

  return (
    <svg className="structural-chart" role="img" viewBox="0 0 280 205" aria-label="Max lag window bar chart">
      <AxisGrid />
      {weights.map((point) => {
        const barWidth = 16;
        const x = 42 + point.lag * 24;
        const h = point.weight * 130;
        return (
          <g key={point.lag}>
            <rect className={point.active ? "chart-bar" : "chart-bar chart-bar--inactive"} height={h} rx="4" width={barWidth} x={x} y={170 - h} />
            {point.active ? <text className="chart-label" x={x - 1} y={Math.max(28, 165 - h)}>{Math.round(point.weight * 100)}%</text> : null}
            <text className="chart-label" x={x - 1} y="195">L{point.lag}</text>
          </g>
        );
      })}
      <line className="chart-marker" x1={42 + profile.maxLag * 24 + 20} x2={42 + profile.maxLag * 24 + 20} y1="20" y2="170" />
    </svg>
  );
}

export function StructuralSettingsPage() {
  const [profile, setProfile] = useState<StructuralProfile>(() => readStoredProfile());
  const readout = useMemo(() => calcReadout(profile), [profile]);

  const updateProfile = (key: keyof StructuralProfile, value: number) => {
    const nextProfile = { ...profile, [key]: key === "maxLag" ? Math.round(value) : value };
    setProfile(nextProfile);
    writeStoredProfile(nextProfile);
  };

  const resetProfile = () => {
    setProfile(defaultProfile);
    writeStoredProfile(defaultProfile);
  };

  return (
    <WorkflowScaffold
      title="Structural Controls"
      summary="Adjust one initial structural profile for carryover and saturation before the audit run."
      nextHelperText="Review & Start Run"
    >
      <section className="structural-layout">
        <div className="structural-main">
          <section className="structural-control-card">
            <div className="structural-control-top">
              <button className="structural-reset-button" type="button" onClick={resetProfile}>
                Reset to Profile Defaults
              </button>
            </div>

            <div className="structural-slider-grid">
              {sliderConfigs.map((config) => (
                <SliderCard
                  config={config}
                  key={config.key}
                  onChange={(value) => updateProfile(config.key, value)}
                  value={profile[config.key]}
                />
              ))}
            </div>

            <div className="structural-info-strip">
              Adjust values and preview impact in real time. Only one final structural profile will be used for the run.
            </div>

            <div className="structural-chart-grid">
              <ChartShell
                title="1. Adstock Memory Curve"
                subtitle="Shows how spend impact decays over time."
                note="Current alpha controls how much media effect carries into future periods."
              >
                <AdstockChart profile={profile} />
              </ChartShell>
              <ChartShell
                title="2. Midpoint Effect"
                subtitle="The spend index where response reaches 50%."
                note="At this spend index, the channel reaches about 50% of maximum response."
              >
                <MidpointChart profile={profile} />
              </ChartShell>
              <ChartShell
                title="3. Slope Sensitivity"
                subtitle="Higher slope means sharper response lift."
                note="Current slope determines how quickly response rises around the midpoint."
              >
                <SlopeChart profile={profile} />
              </ChartShell>
              <ChartShell
                title="4. Max Lag Window"
                subtitle="Defines how many periods carryover extends."
                note="Max lag controls how many past periods can still affect the current response."
              >
                <MaxLagChart profile={profile} />
              </ChartShell>
            </div>
          </section>
        </div>

        <aside className="structural-readout-card">
          <div>
            <h3>Structural Readout</h3>
            <p>Derived metrics for the current profile.</p>
          </div>
          <div className="structural-metric-grid">
            <div><span>Immediate Share</span><strong>{(readout.immediateShare * 100).toFixed(2)}%</strong></div>
            <div><span>Carryover Share</span><strong>{(readout.carryoverShare * 100).toFixed(2)}%</strong></div>
            <div><span>Avg Lag</span><strong>{readout.avgLag.toFixed(3)} periods</strong></div>
            <div><span>Half-Life</span><strong>{readout.halfLife.toFixed(3)} periods</strong></div>
            <div><span>Current Alpha</span><strong>{profile.alphaM.toFixed(2)}</strong></div>
            <div><span>Current ec / slope</span><strong>{profile.ecM.toFixed(2)} / {profile.slopeM.toFixed(2)}</strong></div>
            <div className="structural-metric-wide"><span>Max Lag</span><strong>{profile.maxLag} periods</strong></div>
          </div>
          <div className="structural-readout-note">
            Use this page to explore one structural setting set. After you settle on values, continue to run the audit with this single structural profile.
          </div>
          <NavLink className="structural-primary-action" to="/workflow/review-run">
            Use These Structural Settings
          </NavLink>
          <button className="structural-secondary-action" type="button" onClick={resetProfile}>
            Reset to Profile Defaults
          </button>
        </aside>
      </section>
    </WorkflowScaffold>
  );
}
