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
   *
   * La caméra est placée DERRIÈRE le robot, dans l'axe de son museau : on le
   * voit de dos, et tout ce qui est devant lui occupe l'écran. C'est la même
   * orientation que celle de l'enfant qui se tient derrière le vrai chien —
   * et, en vue lidar, les cubes arrivent donc du bon côté.
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
    /** Posture actuelle ou demandée ('stand' | 'sit' | 'lie_down' | 'balance' | null). */
    posture?: string | null;
    /** Action ou geste en cours ('heart' | 'jump' | 'salute' | 'stretch' | null). */
    action?: string | null;
    /** Position réelle ou simulée du robot (x, y, z en mètres). */
    position?: { x: number; y: number; z: number } | null;
    /** Cap réel ou simulé du robot (en radians). */
    yawRad?: number | null;
    /** Réinitialisation au début d'un nouveau lancement. */
    resetRun?: boolean;
  }

  let {
    volume,
    walking = false,
    interactive = true,
    posture = 'stand',
    action = null,
    position = null,
    yawRad = null,
    resetRun = false,
  }: Props = $props();

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
  let corps: THREE.Object3D | null = null;

  interface PoseConfig {
    bodyY: number;
    pitch: number;
    frontHip: number;
    frontKnee: number;
    frontAnkle: number;
    rearHip: number;
    rearKnee: number;
    rearAnkle: number;
  }

  const POSE_STAND: PoseConfig = {
    bodyY: 0.426,
    pitch: 0,
    frontHip: 0,
    frontKnee: 0,
    frontAnkle: 0,
    rearHip: 0,
    rearKnee: 0,
    rearAnkle: 0,
  };

  const POSE_SIT: PoseConfig = {
    bodyY: 0.255,
    pitch: 27 * (Math.PI / 180),
    frontHip: -0.31,
    frontKnee: -1.06,
    frontAnkle: 1.37,
    rearHip: 0.82,
    rearKnee: -2.35,
    rearAnkle: 1.53,
  };

  const POSE_LIE: PoseConfig = {
    bodyY: 0.125,
    pitch: 0,
    frontHip: 1.14,
    frontKnee: -2.54,
    frontAnkle: 1.40,
    rearHip: 1.14,
    rearKnee: -2.54,
    rearAnkle: 1.40,
  };

  /** Posture demandée en interne ('stand' | 'sit' | 'lie_down'). */
  let postureDemandee = $state<'stand' | 'sit' | 'lie_down'>('stand');

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

  /* ------------------------------------------------------------------ */
  /* La caméra : DERRIÈRE le robot, comme dans un jeu à la 3e personne.  */
  /* ------------------------------------------------------------------ */

  /** Recul de la caméra derrière le robot, en mètres. */
  const CAMERA_RECUL = 1.7;
  /** Hauteur de la caméra au-dessus du sol, en mètres. */
  const CAMERA_HAUTEUR = 1.1;
  /** Longueur visée devant le robot, en mètres. */
  const CAMERA_VISEE = 0.45;
  /** Hauteur du point visé : un peu au-dessus du dos, pour voir devant. */
  const CAMERA_VISEE_Y = 0.45;

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
  /** Cap du robot dans la scène : 0 = museau vers +X. */
  let capChien = 0;

  let robotX = 0;
  let robotZ = 0;
  let robotCap = 0;
  let prevChienX = 0;
  let prevChienZ = 0;

  // Cible de position et cap pour un déplacement continu
  let cibleX = $state(0);
  let cibleZ = $state(0);
  let cibleCap = $state(0);

  // Geste en cours ('heart' | 'jump' | 'salute' | 'stretch' | null)
  let gesteActif = $state<string | null>(null);
  let gesteTemps = 0;

  /**
   * Place la caméra DERRIÈRE le robot, dans l'axe de son museau.
   *
   * C'est la vue à la troisième personne : on voit le chien de dos, et la
   * place devant lui occupe l'écran. La vue lidar s'ouvre de la même façon,
   * pour que les cubes arrivent du bon côté.
   */
  function poserCameraDerriere(): void {
    if (!camera) return;
    const x = chien?.position.x ?? 0;
    const z = chien?.position.z ?? 0;
    // Le museau pointe vers +X quand le cap vaut 0 ; un cap positif tourne
    // vers la GAUCHE du robot, c'est-à-dire vers -Z.
    const avantX = Math.cos(capChien);
    const avantZ = -Math.sin(capChien);
    const viseX = x + avantX * CAMERA_VISEE;
    const viseZ = z + avantZ * CAMERA_VISEE;
    camera.position.set(
      x - avantX * CAMERA_RECUL,
      CAMERA_HAUTEUR,
      z - avantZ * CAMERA_RECUL,
    );
    controles?.target.set(viseX, CAMERA_VISEE_Y, viseZ);
    camera.lookAt(viseX, CAMERA_VISEE_Y, viseZ);
  }

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
    // Position de départ : derrière le robot. Il n'est pas encore chargé,
    // on le suppose à l'origine, museau vers +X.
    camera.position.set(-CAMERA_RECUL, CAMERA_HAUTEUR, 0);

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
    controles.minDistance = 1.2;
    controles.maxDistance = 16;
    controles.maxPolarAngle = Math.PI * 0.52;
    controles.enabled = interactive;
    // Cadrage de départ : la caméra se place derrière le robot.
    poserCameraDerriere();

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
        corps = desc ?? null;
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

    // État courant de la pose pour une interpolation fluide vers la posture cible
    const poseActuelle = {
      bodyY: POSE_STAND.bodyY,
      pitch: POSE_STAND.pitch,
      frontHip: POSE_STAND.frontHip,
      frontKnee: POSE_STAND.frontKnee,
      frontAnkle: POSE_STAND.frontAnkle,
      rearHip: POSE_STAND.rearHip,
      rearKnee: POSE_STAND.rearKnee,
      rearAnkle: POSE_STAND.rearAnkle,
    };

    const animer = (): void => {
      cadre = requestAnimationFrame(animer);

      const maintenant = performance.now();
      const delta = Math.min((maintenant - dernier) / 1000, 0.05);
      dernier = maintenant;

      // Choix de la pose cible selon la posture demandée
      const ciblePose =
        postureDemandee === 'sit'
          ? POSE_SIT
          : postureDemandee === 'lie_down'
            ? POSE_LIE
            : POSE_STAND;

      // Transition progressive vers la posture cible (~1,2 s, mouvement fluide et réaliste)
      const facteur = 1 - Math.exp(-delta * 3.6);
      poseActuelle.bodyY += (ciblePose.bodyY - poseActuelle.bodyY) * facteur;
      poseActuelle.pitch += (ciblePose.pitch - poseActuelle.pitch) * facteur;
      poseActuelle.frontHip += (ciblePose.frontHip - poseActuelle.frontHip) * facteur;
      poseActuelle.frontKnee += (ciblePose.frontKnee - poseActuelle.frontKnee) * facteur;
      poseActuelle.frontAnkle += (ciblePose.frontAnkle - poseActuelle.frontAnkle) * facteur;
      poseActuelle.rearHip += (ciblePose.rearHip - poseActuelle.rearHip) * facteur;
      poseActuelle.rearKnee += (ciblePose.rearKnee - poseActuelle.rearKnee) * facteur;
      poseActuelle.rearAnkle += (ciblePose.rearAnkle - poseActuelle.rearAnkle) * facteur;

      // La marche ne s'enclenche que si le robot est en posture debout
      const estDebout = postureDemandee === 'stand' && poseActuelle.bodyY > 0.35;
      const cibleMarche = marcheDemandee && estDebout ? 1 : 0;
      marche += (cibleMarche - marche) * (1 - Math.exp(-delta * 6));
      if (marche > 0.005) phase += delta * Math.PI * 2 * 1.8;

      if (rig) {
        // Remise à zéro des rotations latérales (roulis/lacet des hanches)
        for (const nom of LEG_NAMES) {
          rig[nom].hip.rotation.x = 0;
          rig[nom].hip.rotation.y = 0;
        }

        const balancement = Math.sin(phase) * marche;
        for (const nom of LEG_NAMES) {
          const patte = rig[nom];
          const isFront = nom === 'FL' || nom === 'FR';
          const baseHip = isFront ? poseActuelle.frontHip : poseActuelle.rearHip;
          const baseKnee = isFront ? poseActuelle.frontKnee : poseActuelle.rearKnee;
          const baseAnkle = isFront ? poseActuelle.frontAnkle : poseActuelle.rearAnkle;

          // Les pattes en diagonale avancent ensemble pendant la marche
          const paire = nom === 'FL' || nom === 'RR' ? balancement : -balancement;
          const levee = Math.max(0, paire);
          const hanche = 0.38 * paire;
          const genou = -0.55 * levee;
          const cheville = -(hanche + genou);

          patte.hip.rotation.z = baseHip + hanche;
          patte.knee.rotation.z = baseKnee + genou;
          patte.ankle.rotation.z = baseAnkle + cheville;
        }
      }

      // Maintien au sol géométrique : les pattes ne s'enfoncent jamais sous la grille
      const cosP = Math.cos(poseActuelle.pitch);
      const sinP = Math.sin(poseActuelle.pitch);
      const L1 = 0.213;
      const L2 = 0.213;

      const calcFootY = (hipX: number, thH: number, thK: number): number => {
        const tx = L1 * Math.sin(thH);
        const ty = -L1 * Math.cos(thH);
        const cx = L2 * Math.sin(thH + thK);
        const cy = -L2 * Math.cos(thH + thK);
        const localX = hipX + tx + cx;
        const localY = ty + cy;
        return localX * sinP + localY * cosP + poseActuelle.bodyY;
      };

      const flY = calcFootY(0.1934, poseActuelle.frontHip, poseActuelle.frontKnee);
      const rlY = calcFootY(-0.1934, poseActuelle.rearHip, poseActuelle.rearKnee);
      const minFoot = Math.min(flY, rlY);
      let hauteurChien = poseActuelle.bodyY;
      if (minFoot < 0) {
        hauteurChien -= minFoot;
      }

      // Animations expressives pour les autres actions (saluer, cœur, s'étirer, sauter)
      if (gesteActif) {
        gesteTemps += delta;
        const duree =
          gesteActif === 'stretch' ? 3.0 : gesteActif === 'jump' ? 1.5 : 2.0;
        const p = Math.min(1.0, gesteTemps / duree);

        if (gesteActif === 'salute') {
          const env = Math.sin(Math.PI * p);
          poseActuelle.pitch += 0.20 * env;
          if (rig) {
            rig.FR.hip.rotation.z += 0.85 * env;
            rig.FR.knee.rotation.z -= 1.10 * env;
            rig.FR.ankle.rotation.z += Math.sin(gesteTemps * Math.PI * 5) * 0.5 * env;
            rig.FR.hip.rotation.y += Math.sin(gesteTemps * Math.PI * 5) * 0.25 * env;
          }
        } else if (gesteActif === 'heart') {
          const env = Math.sin(Math.PI * p);
          poseActuelle.pitch += 0.40 * env;
          hauteurChien -= 0.12 * env;
          if (rig) {
            rig.RL.hip.rotation.z += 0.70 * env;
            rig.RL.knee.rotation.z -= 1.80 * env;
            rig.RR.hip.rotation.z += 0.70 * env;
            rig.RR.knee.rotation.z -= 1.80 * env;
            rig.FL.hip.rotation.z += 0.90 * env;
            rig.FL.knee.rotation.z -= 1.30 * env;
            rig.FL.hip.rotation.x -= 0.35 * env;
            rig.FR.hip.rotation.z += 0.90 * env;
            rig.FR.knee.rotation.z -= 1.30 * env;
            rig.FR.hip.rotation.x += 0.35 * env;
          }
        } else if (gesteActif === 'stretch') {
          const env = Math.sin(Math.PI * p);
          poseActuelle.pitch -= 0.28 * env;
          hauteurChien -= 0.10 * env;
          if (rig) {
            rig.FL.hip.rotation.z += 0.60 * env;
            rig.FL.knee.rotation.z -= 1.10 * env;
            rig.FR.hip.rotation.z += 0.60 * env;
            rig.FR.knee.rotation.z -= 1.10 * env;
            rig.RL.hip.rotation.z -= 0.25 * env;
            rig.RR.hip.rotation.z -= 0.25 * env;
          }
        } else if (gesteActif === 'jump') {
          if (p < 0.3) {
            const c = Math.sin(Math.PI * (p / 0.3));
            hauteurChien -= 0.14 * c;
            if (rig) {
              for (const nom of LEG_NAMES) {
                rig[nom].hip.rotation.z += 0.4 * c;
                rig[nom].knee.rotation.z -= 0.8 * c;
              }
            }
          } else if (p < 0.75) {
            const f = (p - 0.3) / 0.45;
            const h = Math.sin(Math.PI * f);
            hauteurChien += 0.18 * h;
            if (rig) {
              for (const nom of LEG_NAMES) {
                rig[nom].hip.rotation.z += 0.3 * h;
                rig[nom].knee.rotation.z -= 0.5 * h;
              }
            }
          } else {
            const l = Math.sin(Math.PI * (p - 0.75) / 0.25);
            hauteurChien -= 0.08 * l;
            if (rig) {
              for (const nom of LEG_NAMES) {
                rig[nom].hip.rotation.z += 0.25 * l;
                rig[nom].knee.rotation.z -= 0.5 * l;
              }
            }
          }
        }
      }

      // Suivi continu de la position et de l'orientation
      robotX += (cibleX - robotX) * (1 - Math.exp(-delta * 12));
      robotZ += (cibleZ - robotZ) * (1 - Math.exp(-delta * 12));
      robotCap += (cibleCap - robotCap) * (1 - Math.exp(-delta * 12));
      capChien = robotCap;

      if (chien) {
        chien.position.x = robotX;
        chien.position.z = robotZ;
        chien.rotation.y = robotCap + Math.PI / 2;
        chien.position.y = hauteurChien + 0.008 * Math.abs(Math.sin(phase)) * marche;
      }

      if (corps) {
        corps.rotation.z = poseActuelle.pitch;
      }

      // Suivi de la caméra ("la caméra suit")
      if (camera && controles) {
        if (!cameraPlacee) {
          cameraPlacee = true;
          poserCameraDerriere();
          prevChienX = robotX;
          prevChienZ = robotZ;
        } else {
          const deltaX = robotX - prevChienX;
          const deltaZ = robotZ - prevChienZ;
          prevChienX = robotX;
          prevChienZ = robotZ;

          camera.position.x += deltaX;
          camera.position.z += deltaZ;
          controles.target.x += deltaX;
          controles.target.z += deltaZ;

          const avantX = Math.cos(capChien);
          const avantZ = -Math.sin(capChien);
          const viseX = robotX + avantX * CAMERA_VISEE;
          const viseZ = robotZ + avantZ * CAMERA_VISEE;

          controles.target.x += (viseX - controles.target.x) * (1 - Math.exp(-delta * 6));
          controles.target.z += (viseZ - controles.target.z) * (1 - Math.exp(-delta * 6));

          // Quand le robot se déplace ou marche, la caméra se repositionne souplement derrière son cap
          if (walking || Math.abs(deltaX) > 0.0005 || Math.abs(deltaZ) > 0.0005) {
            const camCibleX = robotX - avantX * CAMERA_RECUL;
            const camCibleZ = robotZ - avantZ * CAMERA_RECUL;
            camera.position.x += (camCibleX - camera.position.x) * (1 - Math.exp(-delta * 4));
            camera.position.z += (camCibleZ - camera.position.z) * (1 - Math.exp(-delta * 4));
          }
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

    // Le robot est pose a sa place REELLE dans la carte
    if (donnees?.robot) {
      cibleX = donnees.robot.x ?? 0;
      cibleZ = -(donnees.robot.y ?? 0);
      cibleCap = donnees.robot.cap ?? 0;

      if (!cameraPlacee) {
        cameraPlacee = true;
        poserCameraDerriere();
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
    if (posture === 'sit') {
      postureDemandee = 'sit';
    } else if (posture === 'lie_down') {
      postureDemandee = 'lie_down';
    } else {
      postureDemandee = 'stand';
    }
  });

  $effect(() => {
    if (position) {
      cibleX = position.x;
      cibleZ = -position.y;
    } else if (volume?.robot) {
      cibleX = volume.robot.x ?? 0;
      cibleZ = -(volume.robot.y ?? 0);
    }
    if (yawRad !== null && yawRad !== undefined) {
      cibleCap = yawRad;
    } else if (volume?.robot?.cap !== undefined) {
      cibleCap = volume.robot.cap;
    }
  });

  $effect(() => {
    if (action && action !== gesteActif) {
      gesteActif = action;
      gesteTemps = 0;
    } else if (!action) {
      gesteActif = null;
      gesteTemps = 0;
    }
  });

  $effect(() => {
    if (resetRun) {
      robotX = 0;
      robotZ = 0;
      robotCap = 0;
      cibleX = 0;
      cibleZ = 0;
      cibleCap = 0;
      prevChienX = 0;
      prevChienZ = 0;
      gesteActif = null;
      gesteTemps = 0;
      capChien = 0;
      if (chien) {
        chien.position.x = 0;
        chien.position.z = 0;
        chien.rotation.y = Math.PI / 2;
      }
      poserCameraDerriere();
    }
  });

  $effect(() => {
    if (!controles) return;
    controles.enabled = interactive;
    // On entre dans une vue : on se replace DERRIÈRE le robot, dans l'axe
    // de son museau. En vue lidar, l'enfant peut ensuite tourner autour.
    poserCameraDerriere();
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
