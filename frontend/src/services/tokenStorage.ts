const TOKEN_KEY = "qa_tester_token";
const USERNAME_KEY = "qa_tester_username";

export const tokenStorage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUsername: () => localStorage.getItem(USERNAME_KEY),
  set: (token: string, username: string) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  },
};
