import { requireUser } from '@/lib/auth';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const user = await requireUser();
    const email = user.emailAddresses[0]?.emailAddress ?? '';
    const name = user.firstName
      ? user.lastName
        ? `${user.firstName} ${user.lastName}`
        : user.firstName
      : email.split('@')[0];
    return NextResponse.json({ name, email });
  } catch {
    return NextResponse.json({ name: 'You', email: '' }, { status: 200 });
  }
}
