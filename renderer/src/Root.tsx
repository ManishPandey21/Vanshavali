import { Composition, type CalculateMetadataFunction } from "remotion";
import { EventTimeline } from "./compositions/EventTimeline";
import { FamilyTree } from "./compositions/FamilyTree";
import { FanChart } from "./compositions/FanChart";
import { LifespanTimeline } from "./compositions/LifespanTimeline";
import { PedigreeChart } from "./compositions/PedigreeChart";
import { SAMPLE_PROPS } from "./sample";
import { FPS, totalFrames } from "./timing";
import type { RenderProps } from "./types";

const metadata: CalculateMetadataFunction<RenderProps> = ({ props }) => ({ durationInFrames: totalFrames(props.data) });

const common = { fps: FPS, width: 1280, height: 720, durationInFrames: 300, calculateMetadata: metadata };

export function Root() {
  return (
    <>
      <Composition id="FanChart" component={FanChart} defaultProps={SAMPLE_PROPS.fan} {...common} />
      <Composition id="PedigreeChart" component={PedigreeChart} defaultProps={SAMPLE_PROPS.pedigree} {...common} />
      <Composition id="FamilyTree" component={FamilyTree} defaultProps={SAMPLE_PROPS.family_tree} {...common} />
      <Composition id="LifespanTimeline" component={LifespanTimeline} defaultProps={SAMPLE_PROPS.lifespan} {...common} />
      <Composition id="EventTimeline" component={EventTimeline} defaultProps={SAMPLE_PROPS.event_timeline} {...common} />
    </>
  );
}
