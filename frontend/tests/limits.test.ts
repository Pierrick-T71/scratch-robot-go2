import { describe, it, expect } from 'vitest';
import { computeServiceUrl } from '../src/lib/robot/limits';
import { getWebSocketEventsUrl } from '../src/lib/api/client';

describe('limits — computeServiceUrl', () => {
  it('utilise la même origine en HTTPS pour éviter le blocage Mixed Content', () => {
    const loc = {
      protocol: 'https:',
      hostname: 'optimus.lecreusot.priv',
      port: '',
      origin: 'https://optimus.lecreusot.priv',
    };
    expect(computeServiceUrl(loc)).toBe('https://optimus.lecreusot.priv');
  });

  it('utilise la même origine pour un port standard HTTP 80 derrière un reverse-proxy', () => {
    const loc = {
      protocol: 'http:',
      hostname: 'optimus.lecreusot.priv',
      port: '80',
      origin: 'http://optimus.lecreusot.priv',
    };
    expect(computeServiceUrl(loc)).toBe('http://optimus.lecreusot.priv');
  });

  it('utilise la même origine pour un FQDN domaine privé (optimus.lecreusot.priv)', () => {
    const loc = {
      protocol: 'http:',
      hostname: 'scratch-robot.lecreusot.priv',
      port: '',
      origin: 'http://scratch-robot.lecreusot.priv',
    };
    expect(computeServiceUrl(loc)).toBe('http://scratch-robot.lecreusot.priv');
  });

  it('cible le port direct 8765 en dev local localhost:5173', () => {
    const loc = {
      protocol: 'http:',
      hostname: 'localhost',
      port: '5173',
      origin: 'http://localhost:5173',
    };
    expect(computeServiceUrl(loc)).toBe('http://localhost:8765');
  });

  it('cible le port direct 8765 sur une adresse IP directe sans reverse-proxy', () => {
    const loc = {
      protocol: 'http:',
      hostname: '172.16.13.41',
      port: '5173',
      origin: 'http://172.16.13.41:5173',
    };
    expect(computeServiceUrl(loc)).toBe('http://172.16.13.41:8765');
  });
});

describe('client — getWebSocketEventsUrl', () => {
  it('génère une URL wss:// sécurisée pour une URL de service HTTPS', () => {
    expect(getWebSocketEventsUrl('https://optimus.lecreusot.priv')).toBe(
      'wss://optimus.lecreusot.priv/ws/events',
    );
  });

  it('génère une URL ws:// pour une URL de service HTTP', () => {
    expect(getWebSocketEventsUrl('http://127.0.0.1:8765')).toBe(
      'ws://127.0.0.1:8765/ws/events',
    );
  });

  it('génère une URL wss:// même si un port personnalisé est spécifié en https', () => {
    expect(getWebSocketEventsUrl('https://optimus.lecreusot.priv:8443')).toBe(
      'wss://optimus.lecreusot.priv:8443/ws/events',
    );
  });
});
