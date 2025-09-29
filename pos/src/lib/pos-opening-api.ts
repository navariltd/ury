import { call } from './frappe-sdk';

export interface POSOpeningStatus {
  status: 'not_opened' | 'open';
  opening_entry: string | null;
}

export interface POSOpeningResponse {
  message: POSOpeningStatus;
}

export interface POSCloseValidationResponse {
  message: string;
}

export const checkPOSOpening = async (): Promise<POSOpeningResponse> => {
  try {
    const response = await call.get<POSOpeningResponse>(
      'ury.ury_pos.api.posOpening'
    );
    
    return response.message;
  } catch (error) {
    console.error('Error checking POS opening status:', error);
    throw error;
  }
};

export const validatePOSClose = async (posProfile: string): Promise<POSCloseValidationResponse> => {
  try {
    const response = await call.get<POSCloseValidationResponse>(
      'ury.ury_pos.api.validate_pos_close',
      {
        pos_profile: posProfile
      }
    );
    
    return response;
  } catch (error) {
    console.error('Error validating POS close status:', error);
    throw error;
  }
}; 