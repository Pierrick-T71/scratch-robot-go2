<script lang="ts">
  /**
   * La vue 3D du capteur lidar, comme dans l'application du constructeur.
   *
   * Le lidar publie un VOLUME de voxels : une grille 3D des obstacles
   * autour du robot. On la dessine en petits cubes, colorés selon la
   * hauteur (vert au sol, jaune et orange plus haut, violet au plafond),
   * avec le robot au milieu et la grille du sol.
   *
   * Le modèle 3D du chien vient du fichier `public/model/go2.glb` (modèle
   * public de Sketchfab, CC-BY-4.0). Il est transparent, comme dans
   * l'application : on doit voir le terrain autour des pattes.
   *
   * La même scène sert de vue par défaut, sans les cubes. Quand un bloc de
   * déplacement tourne, les pattes marchent ; sinon, le robot reste immobile.
   */
  import * as THREE from 'three';
  import { onDestroy } from 'svelte';
  import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
  import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
  import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
  import type { LidarVolume } from '../../lib/api/client';

  interface Props {
    volume: LidarVolume | null;
    /** Le robot avance, recule ou tourne : les pattes marchent. */
    walking?: boolean;
    /** La souris peut-elle tourner autour de la scène ? */
    interactive?: boolean;
  }

  let { volume, walking = false, interactive = true }: Props = $props();

  let canvas = $state<HTMLCanvasElement | undefined>();

  /** Les quatre pattes, regroupées autour de leurs vraies articulations. */
  type LegName = 'FL' | 'FR' | 'RL' | 'RR';

  interface LegRig {
    hip: THREE.Group;
    knee: THREE.Group;
    ankle: THREE.Group;
  }

  const LEG_NAMES: readonly LegName[] = ['FL', 'FR', 'RL', 'RR'];

  /**
   * Pivots dans le repère du modèle : x vers l'avant, y vers le haut,
   * z latéral. Les pattes avant sont à x = +0.1934.
   */
  const PIVOTS: Record<LegName, { x: number; z: number }> = {
    FL: { x: 0.1934, z: -0.142 },
    FR: { x: 0.1934, z: 0.142 },
    RL: { x: -0.1934, z: -0.142 },
    RR: { x: -0.1934, z: 0.142 },
  };

  const NODES: Record<
    LegName,
    { thigh: string; calf: string; foot: string; protector: string }
  > = {
    FL: {
      thigh: 'FL_thigh_34',
      calf: 'FL_calf_20',
      foot: 'FL_foot_24',
      protector: 'FL_thigh_protector_36',
    },
    FR: {
      thigh: 'FR_thigh_54',
      calf: 'FR_calf_40',
      foot: 'FR_foot_44',
      protector: 'FR_thigh_protector_56',
    },
    RL: {
      thigh: 'RL_thigh_79',
      calf: 'RL_calf_65',
      foot: 'RL_foot_69',
      protector: 'RL_thigh_protector_81',
    },
    RR: {
      thigh: 'RR_thigh_99',
      calf: 'RR_calf_85',
      foot: 'RR_foot_89',
      protector: 'RR_thigh_protector_101',
    },
  };

  let rig: Record<LegName, LegRig> | null = null;

  /** Recopié depuis la prop : la boucle de rendu le lit à chaque image. */
  let marcheDemandee = $state(false);

  /**
   * Nombre maximal de cubes.
   *
   * Le lidar peut envoyer 50 000 cases ; toutes les dessiner ferait plus
   * d'un million de triangles par image, ce qui sature un rendu logiciel.
   * On garde un échantillon : la vue reste lisible, et la machine respire.
   */
  const MAX_CUBES = 12000;

  /** Pas de rotation : les cubes sont alignes sur la grille. */
  const IDENTITE = new THREE.Quaternion();

  /** La géométrie des cubes : on y met l'échelle de la grille. */
  let geometrie: THREE.BoxGeometry | null = null;
  /** L'échelle actuellement appliquée à la géométrie. */
  let echelleGeometrie = 1;

  let scene: THREE.Scene | null = null;
  let camera: THREE.PerspectiveCamera | null = null;
  let renderer: THREE.WebGLRenderer | null = null;
  let controles: OrbitControls | null = null;
  let cubes: THREE.InstancedMesh | null = null;
  let chien: THREE.Object3D | null = null;
  let cadre = 0;
  /** La camera a-t-elle deja ete posee ? (une seule fois, sinon elle saute) */
  let cameraPlacee = false;

  /** La couleur d'un cube, selon sa hauteur relative. */
  function couleurHauteur(h: number): THREE.Color {
    if (h < 0.22) return new THREE.Color(0x4be86a);
    if (h < 0.45) return new THREE.Color(0xb8e04b);
    if (h < 0.68) return new THREE.Color(0xf2a63c);
    if (h < 0.86) return new THREE.Color(0xd9642a);
    return new THREE.Color(0x8a3fd0);
  }

  /**
   * Regroupe chaque patte autour de ses vraies articulations.
   *
   * Les nœuds du modèle sont des translations pures dans le repère du
   * chien (x vers l'avant, z latéral). On peut donc poser les groupes aux
   * mêmes pivots, sans conversion : une rotation autour de z fait avancer
   * ou reculer la patte.
   */
  function creerRig(desc: THREE.Object3D): Record<LegName, LegRig> | null {
    const resultat = {} as Record<LegName, LegRig>;

    for (const nom of LEG_NAMES) {
      const nœuds = NODES[nom];
      const thigh = desc.getObjectByName(nœuds.thigh);
      const calf = desc.getObjectByName(nœuds.calf);
      const foot = desc.getObjectByName(nœuds.foot);
      const protecteur = desc.getObjectByName(nœuds.protector);
      if (!thigh || !calf || !foot) return null;

      const pivot = PIVOTS[nom];
      const hip = new THREE.Group();
      hip.position.set(pivot.x, 0, pivot.z);
      desc.add(hip);

      const knee = new THREE.Group();
      knee.position.set(0, -0.213, 0);
      hip.add(knee);

      const ankle = new THREE.Group();
      ankle.position.set(0, -0.213, 0);
      knee.add(ankle);

      // `attach` conserve la position de départ : le groupe et le nœud
      // sont au même endroit, la patte ne bouge donc pas d'un pixel.
      hip.attach(thigh);
      if (protecteur) hip.attach(protecteur);
      knee.attach(calf);
      ankle.attach(foot);

      resultat[nom] = { hip, knee, ankle };
    }

    return resultat;
  }

  /** Monte la scène une fois, puis on ne fait que mettre à jour les cubes. */
  function monter(): void {
    if (!canvas || scene) return;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1016);
    scene.fog = new THREE.Fog(0x0d1016, 8, 22);

    camera = new THREE.PerspectiveCamera(48, 1, 0.05, 120);
    camera.position.set(3.4, 2.6, 3.4);

    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      // On garde le dessin : la vue peut alors etre capturee.
      preserveDrawingBuffer: true,
    });
    // Au-delà de 1,5 fois, le rendu logiciel du navigateur ne suit plus.
    renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio ?? 1, 1.5));

    controles = new OrbitControls(camera, canvas);
    controles.enableDamping = true;
    controles.dampingFactor = 0.08;
    controles.target.set(0, 0.1, 0);
    controles.minDistance = 1.2;
    controles.maxDistance = 16;
    controles.maxPolarAngle = Math.PI * 0.52;
    controles.enabled = interactive;

    // La lumiere : une ambiance douce, plus une directionnelle.
    scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x1d2a22, 1.4));
    const directionnelle = new THREE.DirectionalLight(0xffffff, 1.15);
    directionnelle.position.set(3, 6, 2);
    scene.add(directionnelle);

    // La grille du sol, comme dans l'application.
    const sol = new THREE.GridHelper(12, 24, 0x3fa85f, 0x27553a);
    sol.position.y = -0.02;
    scene.add(sol);

    // Le modele du chien.
    const chargeur = new GLTFLoader();
    chargeur.setMeshoptDecoder(MeshoptDecoder);
    chargeur.load(
      '/model/go2.glb',
      (gltf) => {
        const objet = gltf.scene;
        objet.traverse((nœud) => {
          const mesh = nœud as THREE.Mesh;
          if (!mesh.isMesh) return;
          const materiau = mesh.material as THREE.MeshStandardMaterial;
          materiau.transparent = true;
          materiau.opacity = 0.82;
          materiau.depthWrite = false;
        });
        // Le modele de Sketchfab a son AVANT vers +Z et le HAUT vers +Y ;
        // le robot, lui, va vers +X. On tourne donc d'un quart de tour.
        objet.rotation.y = Math.PI / 2;
        // Les pieds du modele sont 42 cm sous son centre : on le pose au sol.
        objet.position.y = 0.426;
        chien = objet;
        scene?.add(objet);

        // Le rig est construit une fois le modèle en place, pour que les
        // matrices du modèle soient à jour.
        objet.updateMatrixWorld(true);
        const desc = objet.getObjectByName('go2_description_102');
        rig = desc ? creerRig(desc) : null;
      },
      undefined,
      () => {
        /* modele absent : la scene reste simplement sans chien */
      },
    );

    // ⚠️ Les cubes du volume sont crees plus tard, dans `majVolume` :
    // leur taille depend de la resolution de la grille, qui n'est connue
    // qu'arrivee la premiere carte. Les creer ici les laisserait a 1 m.

    const redimensionner = (): void => {
      if (!renderer || !camera || !canvas) return;
      const largeur = canvas.clientWidth || 600;
      const hauteur = canvas.clientHeight || 600;
      renderer.setSize(largeur, hauteur, false);
      camera.aspect = largeur / hauteur;
      camera.updateProjectionMatrix();
    };
    redimensionner();
    globalThis.addEventListener('resize', redimensionner);

    let dernier = performance.now();
    let phase = 0;
    let marche = 0;

    const animer = (): void => {
      cadre = requestAnimationFrame(animer);

      const maintenant = performance.now();
      const delta = Math.min((maintenant - dernier) / 1000, 0.05);
      dernier = maintenant;

      // La marche s'installe et s'arrête en douceur.
      const cible = marcheDemandee ? 1 : 0;
      marche += (cible - marche) * (1 - Math.exp(-delta * 6));
      if (marche > 0.005) phase += delta * Math.PI * 2 * 1.8;

      if (rig) {
        const balancement = Math.sin(phase) * marche;
        for (const nom of LEG_NAMES) {
          const patte = rig[nom];
          // Les pattes en diagonale avancent ensemble.
          const paire = nom === 'FL' || nom === 'RR' ? balancement : -balancement;
          const levee = Math.max(0, paire);
          const hanche = 0.38 * paire;
          const genou = -0.55 * levee;
          patte.hip.rotation.z = hanche;
          patte.knee.rotation.z = genou;
          patte.ankle.rotation.z = -(hanche + genou);
        }
        if (chien) {
          // Petit balancement du corps, comme un vrai chien.
          chien.position.y = 0.426 + 0.008 * Math.abs(Math.sin(phase)) * marche;
        }
      }

      controles?.update();
      renderer?.render(scene!, camera!);
    };
    animer();
  }

  /** Replace les cubes a partir du volume recu. */
  function majVolume(donnees: LidarVolume | null): void {
    if (!donnees) {
      if (cubes) cubes.count = 0;
      return;
    }
    let octets: Uint8Array;
    try {
      const binaire = atob(donnees.positions);
      octets = new Uint8Array(binaire.length);
      for (let i = 0; i < binaire.length; i += 1) {
        octets[i] = binaire.charCodeAt(i);
      }
    } catch {
      if (cubes) cubes.count = 0;
      return;
    }

    const origine = donnees.origin;
    const pas = donnees.resolution;
    const nbCases = Math.min(Math.floor(octets.length / 3), MAX_CUBES);

    if (!cubes) {
      // Les cubes font la MOITIE d'une case : a taille pleine ils se
      // touchent et le volume parait gonfle ; a moitie, on voit le relief.
      // ⚠️ Pas de `vertexColors` : les couleurs sont PAR INSTANCE (le volume
      // est colore selon la hauteur), pas par sommet.
      geometrie = new THREE.BoxGeometry(pas * 0.5, pas * 0.5, pas * 0.5);
      const materiau = new THREE.MeshLambertMaterial();
      cubes = new THREE.InstancedMesh(geometrie, materiau, MAX_CUBES);
      // ⚠️ La sphere englobante d'un maillage instancie est calculee une
      // fois : si elle l'est quand il n'y a encore aucun cube, le maillage
      // reste HORS CHAMP ensuite. On desactive le tri.
      cubes.frustumCulled = false;
      cubes.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene?.add(cubes);
    }

    // Les hauteurs, pour colorier chaque cube et poser le sol.
    let minimum = Infinity;
    let maximum = -Infinity;
    for (let i = 2; i < octets.length; i += 3) {
      const z = (origine[2] ?? 0) + (octets[i] ?? 0) * pas;
      if (z < minimum) minimum = z;
      if (z > maximum) maximum = z;
    }
    const etendue = Math.max(0.001, maximum - minimum);

    // Le sol est la case la plus basse : on la met a zero, et le robot avec.
    const solY = minimum;

    const matrice = new THREE.Matrix4();
    for (let i = 0; i < nbCases; i += 1) {
      const x = (origine[0] ?? 0) + (octets[i * 3] ?? 0) * pas;
      const y = (origine[1] ?? 0) + (octets[i * 3 + 1] ?? 0) * pas;
      const z = (origine[2] ?? 0) + (octets[i * 3 + 2] ?? 0) * pas;
      // Le repere du robot : x vers l'avant, y vers sa gauche, z vers le
      // haut. Three.js a Y en haut : on inverse la gauche et la droite.
      matrice.makeTranslation(x, z - solY, -y);
      cubes.setMatrixAt(i, matrice);
      cubes.setColorAt(i, couleurHauteur((z - minimum) / etendue));
    }
    cubes.count = nbCases;
    cubes.instanceMatrix.needsUpdate = true;
    if (cubes.instanceColor) cubes.instanceColor.needsUpdate = true;

    // Le robot est pose a sa place REELLE dans la carte, et il regarde vers
    // son cap reel : c'est ce qui rend la scene credibile.
    if (chien) {
      const pose = donnees.robot ?? { x: 0, y: 0, cap: 0 };
      const x = pose.x ?? 0;
      const z = -(pose.y ?? 0);
      chien.position.set(x, 0.426, z);
      // Le modele de Sketchfab a son avant vers +Z ; on le tourne d'un quart
      // de tour pour qu'il regarde vers l'avant du robot, puis on lui applique
      // le cap mesure.
      chien.rotation.y = (pose.cap ?? 0) + Math.PI / 2;

      // La camera n'est posee qu'UNE fois : sinon chaque nouvelle carte
      // renverrait l'utilisateur a sa position de depart.
      if (!cameraPlacee) {
        cameraPlacee = true;
        controles?.target.set(x, 0.25, z);
        camera?.position.set(x + 2.7, 2.1, z + 2.7);
        camera?.lookAt(x, 0.25, z);
      }
    }
  }

  $effect(() => {
    monter();
  });

  $effect(() => {
    marcheDemandee = walking;
  });

  $effect(() => {
    if (!controles) return;
    controles.enabled = interactive;
    // En revenant à la vue par défaut, on remet le cadrage de départ :
    // cette vue est passive, l'enfant ne pourrait plus le rattraper.
    if (!interactive) {
      const x = chien?.position.x ?? 0;
      const z = chien?.position.z ?? 0;
      controles.target.set(x, 0.1, z);
      camera?.position.set(x + 3.4, 2.6, z + 3.4);
      camera?.lookAt(x, 0.1, z);
    }
  });

  $effect(() => {
    majVolume(volume);
  });

  onDestroy(() => {
    cancelAnimationFrame(cadre);
    controles?.dispose();
    renderer?.dispose();
  });
</script>

<canvas class="lidar" bind:this={canvas}></canvas>

<style>
  .lidar {
    display: block;
    width: 100%;
    height: 100%;
    background: #0d1016;
    touch-action: none;
  }
</style>
