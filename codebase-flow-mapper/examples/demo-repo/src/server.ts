import express from 'express';
import { router } from './routes/index';
import { connect } from '@db/client';
const app = express(); app.use(router); connect(); app.listen(3000);
