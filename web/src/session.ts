export type DemoRole = "operator" | "approver" | "auditor" | "demo-admin";

export class DemoSession {
  private token: string | null = null;

  constructor(private readonly issueToken: (role: DemoRole) => Promise<string>) {}

  async selectRole(role: DemoRole): Promise<void> {
    this.token = null;
    this.token = await this.issueToken(role);
  }

  authorizationHeader(): string {
    if (this.token === null) throw new Error("demo_token_unavailable");
    return `Bearer ${this.token}`;
  }
}
