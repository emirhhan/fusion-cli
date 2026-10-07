const React = require('react');
exports.useCurrentFrame = () => globalThis.__fusionTestFrame ?? 60;
exports.useVideoConfig = () => ({width:1920,height:1080,fps:30,durationInFrames:120});
exports.AbsoluteFill = React.forwardRef(({children,style},ref) => React.createElement('div',{ref,style:{position:'absolute',inset:0,display:'flex',...style}},children));

exports.useDelayRender = () => ({delayRender: () => 1, continueRender: () => {}, cancelRender: error => {throw error;}});

exports.spring = () => globalThis.__fusionTestSpring ?? 1;
exports.interpolate = (v, [a,b], [c,d]) => c + Math.max(0, Math.min(1, (v-a)/(b-a))) * (d-c);
