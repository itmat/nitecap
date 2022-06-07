type User = { name: string; email: string; password: string };

type Environment = {
  baseUrl: string;
  users: User[];
};

export default Environment;
