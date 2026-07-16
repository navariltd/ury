import { call, auth } from './frappe-sdk';

type LoggedUserResponse = string | null;

interface CurrentUserInfo {
  name: string;
  full_name: string;
  roles: string[];
}

export const getLoggedUser = async (): Promise<LoggedUserResponse> => {
  try {
    const response = await auth.getLoggedInUser();
    return response as LoggedUserResponse;
  } catch (error) {
    console.error('Error getting logged user:', error);
    return null;
  }
};

export const getUserRoles = async (email: string): Promise<{ roles: string[]; full_name: string }> => {
  try {
    const response = await call.get('ury.ury_pos.api.get_current_user_info');
    const userInfo = response.message as CurrentUserInfo;

    if (userInfo.name !== email) {
      throw new Error(`Session user mismatch: expected ${email}, received ${userInfo.name}`);
    }

    console.debug('[URY POS] Current user info', userInfo);
    return {
      roles: userInfo.roles,
      full_name: userInfo.full_name,
    };
  } catch (error) {
    console.error('[URY POS] Failed to load current user roles', error);
    throw error;
  }
};

export const logout = async () => {
  try {
    return auth.logout();
  }catch(e){
    console.error('Error logging out:', e);
    return false;
  }
}
