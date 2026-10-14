import { save } from '@db/client';
import { charge } from './payments';
export async function createOrder(b: any) { await charge(b); return save(b); }
