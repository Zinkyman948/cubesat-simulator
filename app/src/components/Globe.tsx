import {
  ArcType,
  Cartesian2,
  Cartesian3,
  ClockRange,
  Color,
  ConstantPositionProperty,
  ImageryLayer,
  Ion,
  JulianDate,
  LabelStyle,
  LagrangePolynomialApproximation,
  PositionPropertyArray,
  SampledPositionProperty,
  TileMapServiceImageryProvider,
  TimeInterval,
  TimeIntervalCollectionProperty,
  VerticalOrigin,
  Viewer,
  buildModuleUrl,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { useEffect, useRef } from "react";
import type { PassRef, SimulationResult } from "../types";

// No Cesium ion services are used: imagery is the Natural Earth II set that
// ships with Cesium, so the globe works offline and needs no API key.
Ion.defaultAccessToken = "";

const SATELLITE = Color.fromCssColorString("#f0efec");
const STATION = Color.fromCssColorString("#eda100");
const CONTACT = Color.fromCssColorString("#0ca30c");
const LABEL_FONT = "12px system-ui, sans-serif";

function orbitPeriodSeconds(result: SimulationResult): number {
  // Mean altitude is enough to size the trail to about one revolution.
  const alts = result.ephemeris.altitude_km;
  const a = 6378.137 + alts.reduce((s, x) => s + x, 0) / alts.length;
  return 2 * Math.PI * Math.sqrt(a ** 3 / 398600.4418);
}

function buildScene(viewer: Viewer, result: SimulationResult) {
  viewer.entities.removeAll();
  const eph = result.ephemeris;
  const times = eph.utc.map((t) => JulianDate.fromIso8601(t));
  const start = times[0];
  const stop = times[times.length - 1];

  const clock = viewer.clock;
  clock.startTime = start.clone();
  clock.stopTime = stop.clone();
  clock.currentTime = start.clone();
  clock.clockRange = ClockRange.LOOP_STOP;
  clock.multiplier = 60;
  clock.shouldAnimate = true;
  viewer.timeline?.zoomTo(start, stop);

  const position = new SampledPositionProperty();
  const nadir = new SampledPositionProperty();
  for (const interp of [position, nadir]) {
    interp.setInterpolationOptions({
      interpolationDegree: 5,
      interpolationAlgorithm: LagrangePolynomialApproximation,
    });
  }
  times.forEach((t, i) => {
    const lon = eph.longitude_deg[i];
    const lat = eph.latitude_deg[i];
    position.addSample(t, Cartesian3.fromDegrees(lon, lat, eph.altitude_km[i] * 1000));
    nadir.addSample(t, Cartesian3.fromDegrees(lon, lat, 0));
  });

  const period = orbitPeriodSeconds(result);
  const satName = result.scenario.spacecraft.name;
  viewer.entities.add({
    id: "satellite",
    name: satName,
    position,
    point: { pixelSize: 9, color: SATELLITE, outlineColor: Color.BLACK, outlineWidth: 2 },
    label: {
      text: satName,
      font: LABEL_FONT,
      style: LabelStyle.FILL_AND_OUTLINE,
      outlineWidth: 3,
      outlineColor: Color.BLACK,
      verticalOrigin: VerticalOrigin.BOTTOM,
      pixelOffset: new Cartesian2(0, -10),
    },
    path: {
      leadTime: period / 2,
      trailTime: period / 2,
      width: 1.5,
      material: SATELLITE.withAlpha(0.7),
      resolution: 60,
    },
  });

  // Sub-satellite point: its path is the ground track for the next/last orbit.
  viewer.entities.add({
    id: "ground-track",
    position: nadir,
    path: {
      leadTime: period,
      trailTime: period,
      width: 1,
      material: SATELLITE.withAlpha(0.35),
      resolution: 60,
    },
  });

  for (const gs of result.scenario.ground_stations) {
    const stationPos = Cartesian3.fromDegrees(gs.longitude_deg, gs.latitude_deg, gs.altitude_m);
    viewer.entities.add({
      id: `station:${gs.name}`,
      name: gs.name,
      position: stationPos,
      point: { pixelSize: 8, color: STATION, outlineColor: Color.BLACK, outlineWidth: 2 },
      label: {
        text: gs.name,
        font: LABEL_FONT,
        style: LabelStyle.FILL_AND_OUTLINE,
        outlineWidth: 3,
        outlineColor: Color.BLACK,
        verticalOrigin: VerticalOrigin.BOTTOM,
        pixelOffset: new Cartesian2(0, -9),
      },
    });

    // Line of sight, shown only while the station has contact: hidden over
    // the whole window, then each pass interval overrides that.
    const show = new TimeIntervalCollectionProperty();
    show.intervals.addInterval(new TimeInterval({ start, stop, data: false }));
    for (const p of result.passes[gs.name] ?? []) {
      show.intervals.addInterval(
        new TimeInterval({
          start: JulianDate.fromIso8601(p.aos),
          stop: JulianDate.fromIso8601(p.los),
          data: true,
        }),
      );
    }

    viewer.entities.add({
      id: `contact:${gs.name}`,
      polyline: {
        positions: new PositionPropertyArray([new ConstantPositionProperty(stationPos), position]),
        show,
        width: 2,
        arcType: ArcType.NONE,
        material: CONTACT,
      },
    });
  }
}

interface Props {
  result: SimulationResult | null;
  selected: PassRef | null;
}

export default function Globe({ result, selected }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const viewer = useRef<Viewer | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const v = new Viewer(container.current, {
      baseLayer: ImageryLayer.fromProviderAsync(
        TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII")),
      ),
      baseLayerPicker: false,
      geocoder: false,
      homeButton: true,
      sceneModePicker: true,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      animation: true,
      timeline: true,
    });
    v.scene.globe.enableLighting = false;
    viewer.current = v;
    return () => {
      v.destroy();
      viewer.current = null;
    };
  }, []);

  useEffect(() => {
    if (viewer.current && result) buildScene(viewer.current, result);
  }, [result]);

  // Jump the clock to the start of the selected pass.
  useEffect(() => {
    const v = viewer.current;
    if (!v || !selected) return;
    v.clock.currentTime = JulianDate.fromIso8601(selected.pass.aos);
    v.clock.multiplier = 10;
    v.clock.shouldAnimate = true;
  }, [selected]);

  return <div className="globe" ref={container} />;
}
