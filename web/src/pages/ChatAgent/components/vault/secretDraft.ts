export interface SecretDraft {
  name: string;
  value: string;
  description: string;
  /** Plaintext toggle on the value field. */
  valueVisible: boolean;
}

export const EMPTY_DRAFT: SecretDraft = {
  name: '',
  value: '',
  description: '',
  valueVisible: false,
};
