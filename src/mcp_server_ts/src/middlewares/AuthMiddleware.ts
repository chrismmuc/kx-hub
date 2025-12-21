/**
 * OAuth middleware for JWT token validation using RS256.
 */

import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { readFileSync } from 'fs';

// JWT Public Key for RS256 token verification
let JWT_PUBLIC_KEY: string;

try {
  // Try local file first (development), then Cloud Run mounted secret
  const localKeyPath = '/secrets/jwt-public-key.pem';
  const cloudRunKeyPath = '/secrets/jwt-public-key/latest';

  try {
    JWT_PUBLIC_KEY = readFileSync(localKeyPath, 'utf8');
    console.log('Loaded JWT public key from local file');
  } catch {
    JWT_PUBLIC_KEY = readFileSync(cloudRunKeyPath, 'utf8');
    console.log('Loaded JWT public key from Cloud Run secret');
  }
} catch (error) {
  console.error('Failed to load JWT public key:', error);
  throw new Error('JWT_PUBLIC_KEY not available');
}

export interface AuthenticatedRequest extends Request {
  userId?: string;
  clientId?: string;
}

export function authMiddleware(req: AuthenticatedRequest, res: Response, next: NextFunction): void {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    res.status(401).json({ error: 'Missing Authorization header' });
    return;
  }

  const parts = authHeader.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer') {
    res.status(401).json({ error: 'Invalid Authorization header format. Expected: Bearer <token>' });
    return;
  }

  const token = parts[1];

  try {
    const decoded = jwt.verify(token, JWT_PUBLIC_KEY, {
      algorithms: ['RS256']
    }) as { sub: string; client_id: string };

    req.userId = decoded.sub;
    req.clientId = decoded.client_id;

    console.log(`Authenticated user: ${req.userId}, client: ${req.clientId}`);
    next();
  } catch (error) {
    console.error('JWT verification failed:', error);
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}
