import { z } from 'zod';

export const learningContainerIdSchema = z
  .string()
  .max(64)
  .regex(
    /^[a-z0-9]+(?:-[a-z0-9]+)*$/,
    '1–64 küçük harf, rakam ve tekli tire kullan.',
  )
  .nullable();

export function validateLearningSettings(
  containerId: string | null,
  delivery: boolean,
) {
  if (!learningContainerIdSchema.safeParse(containerId).success)
    throw new Error(
      'Kit öğrenme kapsayıcı kimliği 1–64 küçük harf, rakam ve tekli tire içermeli.',
    );
  if (delivery && !containerId)
    throw new Error('Kit beceri teslimi bir öğrenme kapsayıcısı gerektirir.');
}
