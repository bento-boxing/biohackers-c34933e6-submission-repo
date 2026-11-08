import type { Metadata } from 'next';
import { Workbench } from '@/components/workbench';
import './globals.css';
export const metadata:Metadata={title:'Agentverse — Research Workbench',description:'An evidence-linked workspace for target discovery, scientific challenge and researcher decisions.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><Workbench>{children}</Workbench></body></html>;}
