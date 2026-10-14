import { Router } from 'express';
import { createOrder } from '../services/orders';
export const router = Router();
router.post('/orders', async (req, res) => res.json(await createOrder(req.body)));
