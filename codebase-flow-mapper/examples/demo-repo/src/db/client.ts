import { PrismaClient } from '@prisma/client';
export const connect = () => new PrismaClient();
export const save = async (x: any) => x;
