// Live2Be Spine 实验 — 成功路径：手动 SkeletonBinary 读 .skel(4.2) → new Spine(skeletonData)。
// 用 pixi-v8 + @esotericsoftware/spine-pixi-v8。
import { Application, Assets } from 'pixi.js';
import { Spine, SkeletonBinary, AtlasAttachmentLoader } from '@esotericsoftware/spine-pixi-v8';

const statusEl = document.getElementById('status');
const animsEl = document.getElementById('anims');
const errEl = document.getElementById('err');
const setStatus = (t) => { statusEl.textContent = t; };
const setErr = (s) => { errEl.textContent = s; };

const ATLAS = './spine/haruka_spr.atlas';
const SKEL = './spine/haruka_spr.skel';

const app = new Application();
try {
  await app.init({ background: '#111111', resizeTo: window, antialias: true });
  document.body.appendChild(app.canvas);
  setStatus('pixi OK. 加载资源…');

  // 加载 .atlas + .skel（spine-pixi-v8 注册了这两类的 Loader）
  await Assets.load([ATLAS, SKEL]);
  const atlas = Assets.get(ATLAS);
  const skel = Assets.get(SKEL);

  // 手动构建 SkeletonData（4.2 二进制）
  const parser = new SkeletonBinary(new AtlasAttachmentLoader(atlas));
  parser.scale = 1;
  const skeletonData = parser.readSkeletonData(skel);

  // 用 SkeletonData 直接构造 Spine（pixi 渲染对象）
  const spine = new Spine(skeletonData);
  spine.position.set(app.screen.width / 2, app.screen.height / 2);
  app.stage.addChild(spine);

  // 居中演示：绑定 bounds 缩放
  const bounds = skeletonData.bones.length;

  setStatus(`✓ Spine 载入成功 · bones=${bounds} · anims=${skeletonData.animations.length}`);
  const anims = skeletonData.animations.map((x) => x.name);
  const skins = skeletonData.skins.map((x) => x.name);

  if (anims.length === 0) {
    setStatus('⚠️ 无动画, skins: ' + skins.join(', '));
  } else {
    anims.forEach((name) => {
      const btn = document.createElement('button');
      btn.textContent = name;
      btn.onclick = () => {
        spine.skeleton.setToSetupPose();
        spine.state.setAnimation(0, name, true);
      };
      animsEl.appendChild(btn);
    });
    setStatus(`动画(${anims.length}): ` + anims.join(', '));
    spine.state.setAnimation(0, anims[0], true);
  }

  window.addEventListener('click', () => {
    console.log('skins:', skins, '| anims:', anims);
  });
} catch (e) {
  console.error(e);
  setErr(String((e && e.stack) || e));
  setStatus('❌ ' + (e && e.message));
}
