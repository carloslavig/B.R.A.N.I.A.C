// Baixa o satélite de um vídeo do Kit Mapas (substitui o scripts/satelite/ que não veio no pacote).
// Mesma conta do render: cameraDoVideo + tilesDoQuadro, quadro a quadro.
// Fonte: dentro de AREA_DE_PERTO = EOxCloudless 2016 (s2cloudless_3857); fora = NASA Blue Marble (GIBS, até z8; acima, recorte ampliado do z8).
// uso: tsx tiles_salvador.ts <kit-mapas> <pasta do vídeo>
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const [kit, video] = process.argv.slice(2);
const imp = (p: string) => import(pathToFileURL(path.join(kit, p)).href);
const r = await imp(`src/videos/${video}/roteiro.ts`);
const { cameraDoVideo } = await imp("src/base/geo/camera.ts");
const { tilesDoQuadro } = await imp("src/base/geo/tiles.ts");

const zmax = r.ZOOM_MAX_TILES ?? 13;
const area: number[] = r.AREA_DE_PERTO ?? [-180, -85, 180, 85];
const precisa = new Set<string>();
for (let q = 0; q <= r.DURACAO; q++) {
  const cam = cameraDoVideo(r.CHAVES, q, r.LARGURA, r.DERIVA ?? 0);
  for (const t of tilesDoQuadro(cam, r.LARGURA, r.ALTURA, zmax)) precisa.add(`${t.z}/${t.x}/${t.y}`);
}
console.log(`${precisa.size} tiles`);

const lon = (x: number, z: number) => (x / 2 ** z) * 360 - 180;
const lat = (y: number, z: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z))) * 180) / Math.PI;
const dentro = (z: number, x: number, y: number) => z >= 9 &&
  lon(x + 1, z) > area[0] && lon(x, z) < area[2] && lat(y, z) > area[1] && lat(y + 1, z) < area[3];

const pub = path.join(kit, "public", r.PASTA_TILES);
const baixa = async (url: string) => {
  for (let i = 0; i < 4; i++) {
    const res = await fetch(url).catch(() => null);
    if (res?.ok) return Buffer.from(await res.arrayBuffer());
    await new Promise((ok) => setTimeout(ok, 1500));
  }
  throw new Error(`falhou: ${url}`);
};
const nasa = (z: number, x: number, y: number) =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/${z}/${y}/${x}.jpeg`;
const eox = (z: number, x: number, y: number) => `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/${z}/${y}/${x}.jpg`;

let feitos = 0;
const fila = [...precisa];
const trabalhador = async () => {
  for (let k = fila.pop(); k; k = fila.pop()) {
    const [z, x, y] = k.split("/").map(Number);
    const arq = path.join(pub, `${z}`, `${x}`, `${y}.jpg`);
    if (fs.existsSync(arq)) continue;
    fs.mkdirSync(path.dirname(arq), { recursive: true });
    if (dentro(z, x, y) || z <= 8) {
      fs.writeFileSync(arq, await baixa(dentro(z, x, y) ? eox(z, x, y) : nasa(z, x, y)));
    } else {
      // fora da área e acima do z8: recorta e amplia o tile z8 da NASA
      const d = z - 8, n = 2 ** d, px = 256 / n;
      const pai = await baixa(nasa(8, x >> d, y >> d));
      const tmp = arq + ".pai.jpg";
      fs.writeFileSync(tmp, pai);
      spawnSync("ffmpeg", ["-v", "error", "-y", "-i", tmp, "-vf", `crop=${px}:${px}:${(x % n) * px}:${(y % n) * px},scale=256:256:flags=bicubic`, "-q:v", "3", arq]);
      fs.rmSync(tmp);
    }
    if (++feitos % 100 === 0) console.log(`${feitos} baixados`);
  }
};
await Promise.all(Array.from({ length: 6 }, trabalhador));
console.log(`pronto: ${feitos} novos em ${pub}`);
