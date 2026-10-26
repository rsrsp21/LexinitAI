import { useEffect, useRef } from "react";

/**
 * Deep-space backdrop: an animated nebula ground with a slow fly-through
 * starfield drawn on top. Two draw calls per frame (fullscreen triangle +
 * one instanced-free gl.POINTS batch), so it stays cheap enough to sit
 * behind scrolling content.
 *
 * Degrades to a plain CSS gradient when WebGL2 is unavailable, and renders a
 * single static frame when the visitor prefers reduced motion.
 */

const STAR_COUNT = 6000;

const NEBULA_VERT = `#version 300 es
precision highp float;
void main() {
  // Fullscreen triangle from gl_VertexID -- no attribute buffer needed.
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const NEBULA_FRAG = `#version 300 es
precision highp float;

uniform vec2  uRes;
uniform float uTime;
uniform vec2  uShift;

out vec4 fragColor;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
    u.y
  );
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p *= 2.03;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  uv += uShift * 0.35;

  float t = uTime * 0.011;
  float n1 = fbm(uv * 2.1 + vec2(t, t * 0.6));
  float n2 = fbm(uv * 3.4 - vec2(t * 0.8, t * 0.4) + n1);

  vec3 deep = vec3(0.014, 0.021, 0.042);
  vec3 dust = vec3(0.120, 0.072, 0.048);
  vec3 cool = vec3(0.032, 0.074, 0.132);

  float d = length(uv);

  vec3 col = deep;
  col += dust * pow(n2, 2.2) * 0.9 * smoothstep(1.2, 0.15, d);
  col += cool * pow(n1, 2.6) * 0.75;

  // Hollow out the middle so headline type stays legible, lift the far edges.
  col *= mix(0.40, 1.35, smoothstep(0.05, 1.15, d));

  fragColor = vec4(col, 1.0);
}`;

const STAR_VERT = `#version 300 es
precision highp float;

in vec3 aSeed;  // xy: position in the field box, z: depth phase
in vec4 aRand;  // x: size, y: palette pick, z: twinkle phase, w: focal offset

uniform float uTime;
uniform float uDpr;
uniform vec2  uShift;
uniform float uBoost;

out vec3  vColor;
out float vSoft;
out float vAlpha;

vec3 palette(float t) {
  if (t < 0.46) return vec3(0.78, 0.86, 1.00);  // pale blue-white
  if (t < 0.70) return vec3(1.00, 1.00, 1.00);  // white
  if (t < 0.85) return vec3(1.00, 0.74, 0.46);  // amber
  if (t < 0.94) return vec3(1.00, 0.52, 0.34);  // ember
  return vec3(0.52, 0.86, 1.00);                // cyan
}

void main() {
  // Each star drifts from far to near, then respawns at the back. Scrolling
  // pushes the whole field forward on top of that, so the page reads as
  // moving through the scene rather than past a backdrop.
  float cycle = fract(aSeed.z + uTime * 0.013 + uBoost);
  float depth = mix(1.55, 0.40, cycle);

  // Nearer stars swing further under pointer/scroll shift -- that offset is
  // the whole parallax effect.
  vec2 ndc = aSeed.xy / depth + uShift / depth;

  // Circle of confusion. Each star gets its own focal plane plus a deadzone
  // where it stays pin-sharp, and the spread term is cubed so only a small
  // tail of stars ever blows out into bokeh -- most stay hard points.
  float focal = 0.70 + aRand.w * 0.70;
  float spread = pow(aRand.z, 6.0);
  float coc = clamp((abs(depth - focal) - 0.22) * 2.4, 0.0, 1.0) * spread;
  vSoft = coc;

  float size = (0.9 + aRand.x * aRand.x * aRand.x * 8.0) / depth;
  size *= 1.0 + coc * 7.0;
  gl_PointSize = clamp(size * uDpr, 0.8, 110.0 * uDpr);

  // Blur spreads the same energy over more pixels, so bokeh reads dimmer.
  float bright = 1.0 / (1.0 + coc * coc * 55.0);
  float life =
    smoothstep(0.0, 0.12, cycle) * (1.0 - smoothstep(0.78, 1.0, cycle));
  float twinkle = 0.74 + 0.26 * sin(uTime * 1.6 + aRand.z * 6.2831853);

  vColor = palette(aRand.y);
  vAlpha = bright * life * twinkle * (0.55 + aRand.x * 0.45);

  gl_Position = vec4(ndc, 0.0, 1.0);
}`;

const STAR_FRAG = `#version 300 es
precision highp float;

in vec3  vColor;
in float vSoft;
in float vAlpha;

out vec4 fragColor;

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(uv, uv);
  if (r2 > 1.0) discard;
  float r = sqrt(r2);

  // In focus: tight gaussian. Out of focus: flat disc with a bright rim,
  // the way a real lens renders an out-of-focus point.
  float core = exp(-r2 * mix(11.0, 1.9, vSoft));
  float disc = smoothstep(1.0, 0.55, r);
  float ring = smoothstep(0.45, 0.92, r) * smoothstep(1.0, 0.9, r);
  // Real bokeh is hollow -- keep the disc faint and let the rim carry it,
  // otherwise thousands of filled discs wash the whole field grey.
  float a = mix(core, disc * 0.26 + ring * 0.5, vSoft);

  // Premultiplied, drawn with additive blending.
  fragColor = vec4(vColor * a * vAlpha, 1.0);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.error("starfield shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function link(gl: WebGL2RenderingContext, vertSrc: string, fragSrc: string) {
  const vert = compile(gl, gl.VERTEX_SHADER, vertSrc);
  const frag = compile(gl, gl.FRAGMENT_SHADER, fragSrc);
  if (!vert || !frag) return null;
  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vert);
  gl.attachShader(program, frag);
  gl.linkProgram(program);
  gl.deleteShader(vert);
  gl.deleteShader(frag);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error("starfield program:", gl.getProgramInfoLog(program));
    return null;
  }
  return program;
}

export function Starfield({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      powerPreference: "low-power",
    });
    if (!gl) return;

    const nebulaProgram = link(gl, NEBULA_VERT, NEBULA_FRAG);
    const starProgram = link(gl, STAR_VERT, STAR_FRAG);
    if (!nebulaProgram || !starProgram) return;

    const nebulaU = {
      res: gl.getUniformLocation(nebulaProgram, "uRes"),
      time: gl.getUniformLocation(nebulaProgram, "uTime"),
      shift: gl.getUniformLocation(nebulaProgram, "uShift"),
    };
    const starU = {
      time: gl.getUniformLocation(starProgram, "uTime"),
      dpr: gl.getUniformLocation(starProgram, "uDpr"),
      shift: gl.getUniformLocation(starProgram, "uShift"),
      boost: gl.getUniformLocation(starProgram, "uBoost"),
    };

    // The field box overshoots NDC so far-away stars still reach the edges.
    // Roughly half the stars are drawn toward the middle to form a denser
    // galactic core, the rest spread flat across the whole box.
    const seeds = new Float32Array(STAR_COUNT * 3);
    const rands = new Float32Array(STAR_COUNT * 4);
    for (let i = 0; i < STAR_COUNT; i++) {
      let x: number;
      let y: number;
      if (i % 2 === 0) {
        const angle = Math.random() * Math.PI * 2;
        // Exponent 0.5 spreads evenly across the disc; nudging above that
        // thickens the core. The floor keeps stars from piling into a knot
        // at dead centre, which reads as an artifact rather than a galaxy.
        const radius = 0.12 + Math.pow(Math.random(), 0.8) * 1.78;
        x = Math.cos(angle) * radius;
        y = Math.sin(angle) * radius * 0.78;
      } else {
        x = (Math.random() * 2 - 1) * 1.9;
        y = (Math.random() * 2 - 1) * 1.9;
      }
      seeds[i * 3 + 0] = x;
      seeds[i * 3 + 1] = y;
      seeds[i * 3 + 2] = Math.random();
      rands[i * 4 + 0] = Math.random();
      rands[i * 4 + 1] = Math.random();
      rands[i * 4 + 2] = Math.random();
      rands[i * 4 + 3] = Math.random();
    }

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);

    const seedBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, seedBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, seeds, gl.STATIC_DRAW);
    const seedLoc = gl.getAttribLocation(starProgram, "aSeed");
    gl.enableVertexAttribArray(seedLoc);
    gl.vertexAttribPointer(seedLoc, 3, gl.FLOAT, false, 0, 0);

    const randBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, randBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, rands, gl.STATIC_DRAW);
    const randLoc = gl.getAttribLocation(starProgram, "aRand");
    gl.enableVertexAttribArray(randLoc);
    gl.vertexAttribPointer(randLoc, 4, gl.FLOAT, false, 0, 0);

    gl.bindVertexArray(null);

    const emptyVao = gl.createVertexArray();

    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE); // additive, shaders output premultiplied

    let dpr = 1;
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
    };
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    // Pointer and scroll both feed the same parallax offset, eased toward the
    // target each frame so motion never snaps.
    const target = { x: 0, y: 0 };
    const shift = { x: 0, y: 0 };
    let boost = 0;

    const onPointer = (event: PointerEvent) => {
      target.x = (event.clientX / window.innerWidth - 0.5) * 0.05;
      target.y = -(event.clientY / window.innerHeight - 0.5) * 0.05;
    };
    // Read per frame rather than on a scroll event: Lenis swallows native
    // scroll events, so a listener here would never fire.
    const readScroll = () => {
      const max = Math.max(1, document.body.scrollHeight - window.innerHeight);
      const progress = window.scrollY / max;
      target.y = -progress * 0.16;
      boost = progress * 0.55;
    };
    window.addEventListener("pointermove", onPointer, { passive: true });
    readScroll();

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    const draw = (time: number) => {
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.useProgram(nebulaProgram);
      gl.uniform2f(nebulaU.res, canvas.width, canvas.height);
      gl.uniform1f(nebulaU.time, time);
      gl.uniform2f(nebulaU.shift, shift.x, shift.y);
      gl.bindVertexArray(emptyVao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      gl.useProgram(starProgram);
      gl.uniform1f(starU.time, time);
      gl.uniform1f(starU.dpr, dpr);
      gl.uniform2f(starU.shift, shift.x, shift.y);
      gl.uniform1f(starU.boost, boost);
      gl.bindVertexArray(vao);
      gl.drawArrays(gl.POINTS, 0, STAR_COUNT);

      gl.bindVertexArray(null);
    };

    let frame = 0;
    let start = 0;

    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (!start) start = now;
      readScroll();
      shift.x += (target.x - shift.x) * 0.045;
      shift.y += (target.y - shift.y) * 0.045;
      draw((now - start) / 1000);
    };

    if (reduced.matches) {
      draw(0);
    } else {
      frame = requestAnimationFrame(loop);
    }

    // Stop burning frames while the tab is in the background.
    const onVisibility = () => {
      if (reduced.matches) return;
      if (document.hidden) {
        cancelAnimationFrame(frame);
        frame = 0;
      } else if (!frame) {
        start = 0;
        frame = requestAnimationFrame(loop);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
      gl.deleteProgram(nebulaProgram);
      gl.deleteProgram(starProgram);
      gl.deleteBuffer(seedBuffer);
      gl.deleteBuffer(randBuffer);
      gl.deleteVertexArray(vao);
      gl.deleteVertexArray(emptyVao);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`block size-full bg-[#04070f] ${className}`}
    />
  );
}
